// Copyright (c) Tailscale Inc & contributors
// SPDX-License-Identifier: BSD-3-Clause

package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"sync"
	"time"

	"golang.org/x/crypto/acme"
	"golang.org/x/crypto/acme/autocert"
	"tailscale.com/tailcfg"
)

var unsafeHostnameCharacters = regexp.MustCompile(`[^a-zA-Z0-9-\.]`)

type certProvider interface {
	// TLSConfig creates a new TLS config suitable for net/http.Server servers.
	//
	// The returned Config must have a GetCertificate function set. The
	// *tls.Certificate values it returns may be shared and cached, so
	// callers must not mutate them.
	TLSConfig() *tls.Config
	// HTTPHandler handle ACME related request, if any.
	HTTPHandler(fallback http.Handler) http.Handler
}

func certProviderByCertMode(mode, dir, hostname string, ipCerts bool, eabKID, eabKey, email string) (certProvider, error) {
	if dir == "" {
		return nil, errors.New("missing required --certdir flag")
	}
	if ipCerts && mode != "letsencrypt" {
		return nil, errors.New("--acme-ip-certs requires --certmode=letsencrypt")
	}
	switch mode {
	case "letsencrypt", "gcp":
		if net.ParseIP(hostname) != nil {
			if mode == "gcp" {
				return nil, errors.New("--certmode=gcp requires --hostname to be a DNS name, not an IP address")
			}
			if !ipCerts {
				return nil, errors.New("--hostname is an IP address; use --certmode=manual for a self-signed cert, or set --acme-ip-certs to get LetsEncrypt IP address certs")
			}
			// IP-only server: certs are issued on demand per
			// connection, so there is no hostname cert provider.
			return newIPCertManager(dir, email, "", nil)
		}
		certManager := &autocert.Manager{
			Prompt:     autocert.AcceptTOS,
			HostPolicy: autocert.HostWhitelist(hostname),
			Cache:      autocert.DirCache(dir),
		}
		if mode == "gcp" {
			if eabKID == "" || eabKey == "" {
				return nil, errors.New("--certmode=gcp requires --acme-eab-kid and --acme-eab-key flags")
			}
			if email == "" {
				return nil, errors.New("--certmode=gcp requires --acme-email flag")
			}
			keyBytes, err := decodeEABKey(eabKey)
			if err != nil {
				return nil, err
			}
			certManager.Client = &acme.Client{
				DirectoryURL: "https://dv.acme-v02.api.pki.goog/directory",
			}
			certManager.ExternalAccountBinding = &acme.ExternalAccountBinding{
				KID: eabKID,
				Key: keyBytes,
			}
		}
		if hostname == "derp.tailscale.com" {
			certManager.HostPolicy = prodAutocertHostPolicy
		}
		if email != "" {
			certManager.Email = email
		} else if hostname == "derp.tailscale.com" {
			certManager.Email = "security@tailscale.com"
		}
		if ipCerts {
			return newIPCertManager(dir, email, "", certManager)
		}
		return certManager, nil
	case "manual":
		return NewManualCertManager(dir, hostname)
	default:
		return nil, fmt.Errorf("unsupport cert mode: %q", mode)
	}
}

// Reload checks run on handshakes, with bounded file I/O and no background
// goroutine. Mount the certificate directory, not individual live symlink files.
const (
	manualCertReloadInterval  = time.Second
	manualCertWarningInterval = time.Minute
)

type manualCertManager struct {
	mu                  sync.Mutex       // protects cert and nextReload
	cert                *tls.Certificate // immutable after publication
	crtPath             string
	keyPath             string
	nextReload          time.Time
	nextWarning         time.Time
	reloadFailureWarned bool
	logf                func(string, ...any) // immutable after construction; called under mu
	hostname            string               // hostname or IP address of server
	noHostname          bool                 // whether hostname is an IP address
}

// validateManualCertificate checks the identity and validity of a key-matched
// pair loaded by crypto/tls. It does not replace clients' chain/trust validation.
func validateManualCertificate(cert *tls.Certificate, hostname string, now time.Time) error {
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		return errors.New("cannot parse manual certificate")
	}
	if err := leaf.VerifyHostname(hostname); err != nil {
		return errors.New("manual certificate does not match configured hostname")
	}
	if now.Before(leaf.NotBefore) || !now.Before(leaf.NotAfter) {
		return errors.New("manual certificate is not currently valid")
	}
	cert.Leaf = leaf
	return nil
}

// NewManualCertManager loads a valid certificate on startup and refreshes it on handshakes.
func NewManualCertManager(certdir, hostname string) (certProvider, error) {
	keyname := unsafeHostnameCharacters.ReplaceAllString(hostname, "")
	crtPath := filepath.Join(certdir, keyname+".crt")
	keyPath := filepath.Join(certdir, keyname+".key")
	cert, err := tls.LoadX509KeyPair(crtPath, keyPath)
	hostnameIP := net.ParseIP(hostname) // or nil if hostname isn't an IP address
	if err != nil {
		// If the hostname is an IP address, automatically create a
		// self-signed certificate for it.
		var certp *tls.Certificate
		if os.IsNotExist(err) && hostnameIP != nil {
			certp, err = createSelfSignedIPCert(crtPath, keyPath, hostname)
		}
		if err != nil {
			return nil, fmt.Errorf("can not load x509 key pair for hostname %q: %w", keyname, err)
		}
		cert = *certp
	}
	now := time.Now()
	if err := validateManualCertificate(&cert, hostname, now); err != nil {
		return nil, err
	}
	x509Cert := cert.Leaf
	if hostnameIP != nil {
		// If the hostname is an IP address, print out information on how to
		// confgure this in the derpmap.
		dn := &tailcfg.DERPNode{
			Name:     "custom",
			RegionID: 900,
			HostName: hostname,
			CertName: fmt.Sprintf("sha256-raw:%-02x", sha256.Sum256(x509Cert.Raw)),
		}
		dnJSON, _ := json.Marshal(dn)
		log.Printf("Using self-signed certificate for IP address %q. Configure it in DERPMap using: (https://tailscale.com/s/custom-derp)\n  %s", hostname, dnJSON)
	}
	return &manualCertManager{
		cert:       &cert,
		crtPath:    crtPath,
		keyPath:    keyPath,
		nextReload: now.Add(manualCertReloadInterval),
		logf:       log.Printf,
		hostname:   hostname,
		noHostname: net.ParseIP(hostname) != nil,
	}, nil
}

func (m *manualCertManager) TLSConfig() *tls.Config {
	return &tls.Config{
		Certificates: nil,
		NextProtos: []string{
			"http/1.1",
		},
		GetCertificate: m.getCertificate,
	}
}

func (m *manualCertManager) getCertificate(hi *tls.ClientHelloInfo) (*tls.Certificate, error) {
	if hi.ServerName != m.hostname && !m.noHostname {
		return nil, fmt.Errorf("cert mismatch with hostname: %q", hi.ServerName)
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now()
	if !now.Before(m.nextReload) {
		// A split renewal may temporarily contain an incomplete or mismatched
		// pair. Publish only a fully parsed, key-matched, currently valid
		// certificate; otherwise preserve the last good immutable pair.
		candidate, err := tls.LoadX509KeyPair(m.crtPath, m.keyPath)
		if err == nil {
			err = validateManualCertificate(&candidate, m.hostname, time.Now())
		}
		now = time.Now()
		if err == nil {
			m.cert = &candidate
			if m.reloadFailureWarned {
				m.logf("manual certificate reload recovered")
				m.reloadFailureWarned = false
			}
		} else if !now.Before(m.nextWarning) {
			// Fixed messages omit certificate, key, hostname, path and raw error.
			// Keep the warning budget across recoveries so flapping cannot flood.
			m.logf("WARNING: manual certificate reload rejected; cached certificate unchanged")
			m.reloadFailureWarned = true
			m.nextWarning = now.Add(manualCertWarningInterval)
		}
		// Start the interval after I/O so a slow read cannot cause retries on
		// every subsequent handshake.
		m.nextReload = time.Now().Add(manualCertReloadInterval)
	}
	now = time.Now()
	if now.Before(m.cert.Leaf.NotBefore) || !now.Before(m.cert.Leaf.NotAfter) {
		return nil, errors.New("no currently valid manual certificate available")
	}

	// TLS callers share immutable certificate data. Clamp the chain capacity
	// so appending DERP metadata cannot overwrite the manager's chain storage.
	certCopy := *m.cert
	certCopy.Certificate = slices.Clip(certCopy.Certificate)
	return &certCopy, nil
}

func (m *manualCertManager) HTTPHandler(fallback http.Handler) http.Handler {
	return fallback
}

func createSelfSignedIPCert(crtPath, keyPath, ipStr string) (*tls.Certificate, error) {
	ip := net.ParseIP(ipStr)
	if ip == nil {
		return nil, fmt.Errorf("invalid IP address: %s", ipStr)
	}

	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, fmt.Errorf("failed to generate EC private key: %v", err)
	}

	serialNumberLimit := new(big.Int).Lsh(big.NewInt(1), 128)
	serialNumber, err := rand.Int(rand.Reader, serialNumberLimit)
	if err != nil {
		return nil, fmt.Errorf("failed to generate serial number: %v", err)
	}

	now := time.Now()
	template := x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			CommonName: ipStr,
		},
		NotBefore: now,
		NotAfter:  now.AddDate(1, 0, 0), // expires in 1 year; a bit over that is rejected by macOS etc

		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
	}

	// Set the IP as a SAN.
	template.IPAddresses = []net.IP{ip}

	// Create the self-signed certificate.
	derBytes, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		return nil, fmt.Errorf("failed to create certificate: %v", err)
	}

	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: derBytes})

	keyBytes, err := x509.MarshalECPrivateKey(priv)
	if err != nil {
		return nil, fmt.Errorf("unable to marshal EC private key: %v", err)
	}

	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyBytes})

	if err := os.MkdirAll(filepath.Dir(crtPath), 0700); err != nil {
		return nil, fmt.Errorf("failed to create directory for certificate: %v", err)
	}
	if err := os.WriteFile(crtPath, certPEM, 0644); err != nil {
		return nil, fmt.Errorf("failed to write certificate to %s: %v", crtPath, err)
	}
	if err := os.WriteFile(keyPath, keyPEM, 0600); err != nil {
		return nil, fmt.Errorf("failed to write key to %s: %v", keyPath, err)
	}

	tlsCert, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		return nil, fmt.Errorf("failed to create tls.Certificate: %v", err)
	}
	return &tlsCert, nil
}

// decodeEABKey decodes a base64-encoded EAB key.
// It accepts both standard base64 (with padding) and base64url (without padding).
func decodeEABKey(s string) ([]byte, error) {
	// Try base64url first (no padding), then standard base64 (with padding).
	// This handles both ACME spec format and gcloud output format.
	if b, err := base64.RawURLEncoding.DecodeString(s); err == nil {
		return b, nil
	}
	if b, err := base64.StdEncoding.DecodeString(s); err == nil {
		return b, nil
	}
	return nil, errors.New("invalid base64 encoding for EAB key")
}
