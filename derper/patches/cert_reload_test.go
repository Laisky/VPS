// Copyright (c) Tailscale Inc & contributors
// SPDX-License-Identifier: BSD-3-Clause
//
// Regression coverage for the local manual-certificate reload overlay, based
// exactly on tailscale.com v1.102.5. All private keys below are generated fixtures.
package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

const reloadTestHostname = "derp.test"

type generatedManualPair struct{ cert, key []byte }

func generatedReloadPair(t *testing.T, serial int64, hostname string, before, after time.Time) generatedManualPair {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	leaf := &x509.Certificate{
		SerialNumber: big.NewInt(serial), DNSNames: []string{hostname},
		NotBefore: before, NotAfter: after,
		KeyUsage:    x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, leaf, leaf, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	pk, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return generatedManualPair{
		cert: pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		key:  pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pk}),
	}
}

func validReloadPair(t *testing.T, serial int64) generatedManualPair {
	t.Helper()
	now := time.Now()
	return generatedReloadPair(t, serial, reloadTestHostname, now.Add(-time.Hour), now.Add(time.Hour))
}

func writeReloadPair(t *testing.T, dir string, p generatedManualPair) {
	t.Helper()
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	for ext, data := range map[string][]byte{".crt": p.cert, ".key": p.key} {
		name := filepath.Join(dir, reloadTestHostname+ext)
		if data == nil {
			if err := os.Remove(name); err != nil && !os.IsNotExist(err) {
				t.Fatal(err)
			}
		} else if err := os.WriteFile(name, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
}

func reloadTestManager(t *testing.T, dir string) *manualCertManager {
	t.Helper()
	cp, err := NewManualCertManager(dir, reloadTestHostname)
	if err != nil {
		t.Fatal(err)
	}
	return cp.(*manualCertManager)
}

func forceManualReload(m *manualCertManager) {
	m.mu.Lock()
	m.nextReload = time.Time{}
	m.mu.Unlock()
}

func reloadSerial(m *manualCertManager) (int64, error) {
	cert, err := m.TLSConfig().GetCertificate(&tls.ClientHelloInfo{ServerName: reloadTestHostname})
	if err != nil {
		return 0, err
	}
	return cert.Leaf.SerialNumber.Int64(), nil
}

func wantReloadSerial(t *testing.T, m *manualCertManager, want int64) {
	t.Helper()
	got, err := reloadSerial(m)
	if err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("certificate serial = %d; want %d", got, want)
	}
}

func TestManualCertReloadRenewalAndThrottle(t *testing.T) {
	dir := t.TempDir()
	writeReloadPair(t, dir, validReloadPair(t, 1))
	m := reloadTestManager(t, dir)
	writeReloadPair(t, dir, validReloadPair(t, 2))
	// The initial one-second window bounds disk reads during handshake bursts.
	wantReloadSerial(t, m, 1)
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
}

func invalidReloadPairs(t *testing.T) map[string]generatedManualPair {
	t.Helper()
	now := time.Now()
	valid := validReloadPair(t, 2)
	other := validReloadPair(t, 3)
	return map[string]generatedManualPair{
		"mismatched-key":        {valid.cert, other.key},
		"wrong-hostname":        generatedReloadPair(t, 2, "other.test", now.Add(-time.Hour), now.Add(time.Hour)),
		"expired":               generatedReloadPair(t, 2, reloadTestHostname, now.Add(-2*time.Hour), now.Add(-time.Hour)),
		"future":                generatedReloadPair(t, 2, reloadTestHostname, now.Add(time.Hour), now.Add(2*time.Hour)),
		"malformed-certificate": {[]byte("incomplete certificate"), valid.key},
		"malformed-key":         {valid.cert, []byte("incomplete key")},
		"missing-certificate":   {nil, valid.key},
		"missing-key":           {valid.cert, nil},
		"empty-certificate":     {[]byte{}, valid.key},
		"empty-key":             {valid.cert, []byte{}},
	}
}

func TestManualCertReloadInvalidUpdateKeepsLastValid(t *testing.T) {
	for name, bad := range invalidReloadPairs(t) {
		t.Run(name, func(t *testing.T) {
			dir := t.TempDir()
			writeReloadPair(t, dir, validReloadPair(t, 1))
			m := reloadTestManager(t, dir)
			writeReloadPair(t, dir, bad)
			forceManualReload(m)
			wantReloadSerial(t, m, 1)
			// A rejected candidate never prevents a later successful renewal.
			writeReloadPair(t, dir, validReloadPair(t, 4))
			forceManualReload(m)
			wantReloadSerial(t, m, 4)
		})
	}
}

func TestManualCertReloadInvalidStartupFails(t *testing.T) {
	for name, bad := range invalidReloadPairs(t) {
		t.Run(name, func(t *testing.T) {
			dir := t.TempDir()
			writeReloadPair(t, dir, bad)
			if _, err := NewManualCertManager(dir, reloadTestHostname); err == nil {
				t.Fatal("invalid startup certificate was accepted")
			}
		})
	}
}

func TestManualCertReloadSplitReplacement(t *testing.T) {
	dir := t.TempDir()
	old, next := validReloadPair(t, 1), validReloadPair(t, 2)
	writeReloadPair(t, dir, old)
	m := reloadTestManager(t, dir)
	// Certificate first, old private key still present.
	writeReloadPair(t, dir, generatedManualPair{next.cert, old.key})
	forceManualReload(m)
	wantReloadSerial(t, m, 1)
	writeReloadPair(t, dir, next)
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
	// Private key first in the next rotation.
	writeReloadPair(t, dir, generatedManualPair{next.cert, old.key})
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
	writeReloadPair(t, dir, old)
	forceManualReload(m)
	wantReloadSerial(t, m, 1)
}

func switchReloadDirectory(dir, target string) error {
	temp := filepath.Join(dir, "next")
	if err := os.Symlink(target, temp); err != nil {
		return err
	}
	return os.Rename(temp, filepath.Join(dir, "current"))
}

func TestManualCertReloadAtomicDirectoryReplacement(t *testing.T) {
	dir := t.TempDir()
	writeReloadPair(t, filepath.Join(dir, "one"), validReloadPair(t, 1))
	writeReloadPair(t, filepath.Join(dir, "two"), validReloadPair(t, 2))
	if err := switchReloadDirectory(dir, "one"); err != nil {
		t.Fatal(err)
	}
	m := reloadTestManager(t, filepath.Join(dir, "current"))
	if err := switchReloadDirectory(dir, "two"); err != nil {
		t.Fatal(err)
	}
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
}

func TestManualCertReloadConcurrentRotation(t *testing.T) {
	dir := t.TempDir()
	writeReloadPair(t, filepath.Join(dir, "one"), validReloadPair(t, 1))
	writeReloadPair(t, filepath.Join(dir, "two"), validReloadPair(t, 2))
	if err := switchReloadDirectory(dir, "one"); err != nil {
		t.Fatal(err)
	}
	m := reloadTestManager(t, filepath.Join(dir, "current"))
	var wg sync.WaitGroup
	errs := make(chan error, 9)
	for range 8 {
		wg.Go(func() {
			for range 40 {
				forceManualReload(m)
				n, err := reloadSerial(m)
				if err != nil {
					errs <- err
					return
				}
				if n != 1 && n != 2 {
					errs <- fmt.Errorf("unexpected certificate serial %d", n)
					return
				}
			}
		})
	}
	wg.Go(func() {
		for i := range 40 {
			target := "one"
			if i%2 == 1 {
				target = "two"
			}
			if err := switchReloadDirectory(dir, target); err != nil {
				errs <- err
				return
			}
		}
	})
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
}

func TestManualCertReloadDoesNotServeExpiredFallback(t *testing.T) {
	dir := t.TempDir()
	deadline := time.Now().Truncate(time.Second).Add(2 * time.Second)
	pair := generatedReloadPair(t, 1, reloadTestHostname, time.Now().Add(-time.Hour), deadline)
	writeReloadPair(t, dir, pair)
	m := reloadTestManager(t, dir)
	wantReloadSerial(t, m, 1)
	writeReloadPair(t, dir, generatedManualPair{[]byte("partial"), pair.key})
	time.Sleep(time.Until(deadline.Add(20 * time.Millisecond)))
	if _, err := reloadSerial(m); err == nil {
		t.Fatal("expired fallback certificate was served")
	}
}

func TestManualCertReloadSNIAndHTTPHandler(t *testing.T) {
	dir := t.TempDir()
	writeReloadPair(t, dir, validReloadPair(t, 1))
	m := reloadTestManager(t, dir)
	if _, err := m.TLSConfig().GetCertificate(&tls.ClientHelloInfo{ServerName: "other.test"}); err == nil {
		t.Fatal("wrong SNI accepted")
	}
	fallback := http.NewServeMux()
	if m.HTTPHandler(fallback) != fallback {
		t.Fatal("manual mode changed HTTP handler")
	}
}

func TestManualCertificateValidityBoundaries(t *testing.T) {
	now := time.Now().Truncate(time.Second)
	p := generatedReloadPair(t, 1, reloadTestHostname, now, now.Add(time.Hour))
	cert, err := tls.X509KeyPair(p.cert, p.key)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateManualCertificate(&cert, reloadTestHostname, now); err != nil {
		t.Fatalf("NotBefore boundary rejected: %v", err)
	}
	if err := validateManualCertificate(&cert, reloadTestHostname, now.Add(time.Hour)); err == nil {
		t.Fatal("NotAfter boundary accepted")
	}
}

func captureManualReloadLogs(m *manualCertManager) *[]string {
	logs := new([]string)
	m.logf = func(format string, args ...any) {
		*logs = append(*logs, fmt.Sprintf(format, args...))
	}
	return logs
}

func TestManualCertReloadWarningsInvalidAndRecovery(t *testing.T) {
	for name, bad := range invalidReloadPairs(t) {
		t.Run(name, func(t *testing.T) {
			dir := t.TempDir()
			writeReloadPair(t, dir, validReloadPair(t, 1))
			m := reloadTestManager(t, dir)
			logs := captureManualReloadLogs(m)
			writeReloadPair(t, dir, bad)
			for range 64 {
				forceManualReload(m)
				wantReloadSerial(t, m, 1)
			}
			if len(*logs) != 1 || (*logs)[0] != "WARNING: manual certificate reload rejected; cached certificate unchanged" {
				t.Fatalf("unexpected warning records: %q", *logs)
			}
			writeReloadPair(t, dir, validReloadPair(t, 4))
			forceManualReload(m)
			wantReloadSerial(t, m, 4)
			if len(*logs) != 2 || (*logs)[1] != "manual certificate reload recovered" {
				t.Fatalf("unexpected recovery records: %q", *logs)
			}
			for range 16 {
				forceManualReload(m)
				wantReloadSerial(t, m, 4)
			}
			if len(*logs) != 2 {
				t.Fatalf("healthy rechecks logged repeatedly: %q", *logs)
			}
		})
	}
}

func TestManualCertReloadWarningBudgetSurvivesFlapping(t *testing.T) {
	dir := t.TempDir()
	old, good := validReloadPair(t, 1), validReloadPair(t, 2)
	bad := generatedManualPair{good.cert, old.key}
	writeReloadPair(t, dir, old)
	m := reloadTestManager(t, dir)
	logs := captureManualReloadLogs(m)
	for i := range 32 {
		writeReloadPair(t, dir, bad)
		forceManualReload(m)
		want := int64(2)
		if i == 0 {
			want = 1
		}
		wantReloadSerial(t, m, want)
		writeReloadPair(t, dir, good)
		forceManualReload(m)
		wantReloadSerial(t, m, 2)
	}
	if len(*logs) != 2 {
		t.Fatalf("flapping bypassed warning budget: %q", *logs)
	}
	// Simulate the elapsed warning interval without sleeping for a minute.
	m.mu.Lock()
	m.nextWarning = time.Time{}
	m.mu.Unlock()
	writeReloadPair(t, dir, bad)
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
	if len(*logs) != 3 {
		t.Fatalf("persistent rejection did not warn after interval: %q", *logs)
	}
	writeReloadPair(t, dir, good)
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
	if len(*logs) != 4 || (*logs)[3] != "manual certificate reload recovered" {
		t.Fatalf("second logged failure did not recover: %q", *logs)
	}
}

func TestManualCertReloadObservabilityConcurrent(t *testing.T) {
	dir := t.TempDir()
	old, good := validReloadPair(t, 1), validReloadPair(t, 2)
	writeReloadPair(t, dir, old)
	m := reloadTestManager(t, dir)
	logs := captureManualReloadLogs(m)
	writeReloadPair(t, dir, generatedManualPair{good.cert, old.key})
	var wg sync.WaitGroup
	errs := make(chan error, 16)
	for range 16 {
		wg.Go(func() {
			for range 8 {
				forceManualReload(m)
				serial, err := reloadSerial(m)
				if err != nil {
					errs <- err
					return
				}
				if serial != 1 {
					errs <- fmt.Errorf("fallback serial=%d", serial)
					return
				}
			}
		})
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
	if len(*logs) != 1 {
		t.Fatalf("concurrent failures flooded warnings: %q", *logs)
	}
	writeReloadPair(t, dir, good)
	forceManualReload(m)
	wantReloadSerial(t, m, 2)
	if len(*logs) != 2 || (*logs)[1] != "manual certificate reload recovered" {
		t.Fatalf("missing recovery after concurrent failures: %q", *logs)
	}
}
