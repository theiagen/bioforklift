#!/bin/bash

# Create SSL directory
mkdir -p ssl

# Generate self-signed certificate for development
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes \
  -subj "/C=US/ST=Development/L=Local/O=Bioforklift/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

echo "SSL certificates generated in ssl/ directory"