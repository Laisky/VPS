package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestManualCertReloadBaseline(t *testing.T) {
	const host = "derp.test"
	dir := t.TempDir()
	writePair := func(serial int64) {
		t.Helper()
		key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			t.Fatal(err)
		}
		now := time.Now()
		leaf := &x509.Certificate{SerialNumber: big.NewInt(serial), DNSNames: []string{host}, NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
		der, err := x509.CreateCertificate(rand.Reader, leaf, leaf, &key.PublicKey, key)
		if err != nil {
			t.Fatal(err)
		}
		pk, err := x509.MarshalPKCS8PrivateKey(key)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, host+".crt"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0600); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, host+".key"), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pk}), 0600); err != nil {
			t.Fatal(err)
		}
	}
	writePair(1)
	cp, err := NewManualCertManager(dir, host)
	if err != nil {
		t.Fatal(err)
	}
	writePair(2)
	time.Sleep(1100 * time.Millisecond)
	cert, err := cp.TLSConfig().GetCertificate(&tls.ClientHelloInfo{ServerName: host})
	if err != nil {
		t.Fatal(err)
	}
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	if got := leaf.SerialNumber.Int64(); got != 2 {
		t.Fatalf("after valid on-disk renewal got certificate serial %d; want 2", got)
	}
}

// This test runs against both unmodified upstream and the patched manager.
func TestManualCertStartupValidityCompatibility(t *testing.T) {
	const host = "derp.test"
	now := time.Now()
	for _, tc := range []struct {
		name          string
		before, after time.Time
		dns           string
		wantError     bool
	}{
		{"valid", now.Add(-time.Hour), now.Add(time.Hour), host, false},
		{"expired", now.Add(-2 * time.Hour), now.Add(-time.Hour), host, false},
		{"future", now.Add(time.Hour), now.Add(2 * time.Hour), host, false},
		{"wrong-host", now.Add(-time.Hour), now.Add(time.Hour), "other.test", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
			if err != nil {
				t.Fatal(err)
			}
			leaf := &x509.Certificate{SerialNumber: big.NewInt(42), DNSNames: []string{tc.dns}, NotBefore: tc.before, NotAfter: tc.after, KeyUsage: x509.KeyUsageDigitalSignature}
			der, err := x509.CreateCertificate(rand.Reader, leaf, leaf, &key.PublicKey, key)
			if err != nil {
				t.Fatal(err)
			}
			pk, err := x509.MarshalPKCS8PrivateKey(key)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(dir, host+".crt"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0600); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(dir, host+".key"), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pk}), 0600); err != nil {
				t.Fatal(err)
			}
			_, err = NewManualCertManager(dir, host)
			if (err != nil) != tc.wantError {
				t.Fatalf("startup error = %v, wantError %v", err, tc.wantError)
			}
		})
	}
}
