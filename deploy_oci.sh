#!/bin/bash
# Vynce OCI Deployment Script
# This script installs Docker, configures firewalls, and runs Vynce via Docker Compose.

echo "Installing Docker and Docker Compose..."
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

echo "Starting Docker service..."
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

echo "Configuring firewall rules to open ports 80, 443, and 8000..."
# OCI Ubuntu VM iptables configuration to permit incoming TCP traffic
sudo iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save

echo "Creating template .env file if it does not exist..."
if [ ! -f .env ]; then
  cat <<EOT > .env
# Vynce Environment Variables
JWT_SECRET=$(openssl rand -hex 32)
JAMENDO_CLIENT_ID=94663265
HOST=0.0.0.0
PORT=8000
MAX_ROOM_SIZE=20
JWT_EXPIRY_HOURS=72
DATABASE_URL=postgresql://vynce:vyncepassword@db:5432/vyncedb
EOT
  echo "Template .env created. You can edit it to change default passwords."
fi

echo "Building and running docker containers..."
sudo docker-compose up -d --build

echo "Vynce deployed successfully!"
echo "Make sure you have added Ingress Rules for ports 80, 443, and 8000 in your OCI Dashboard."
