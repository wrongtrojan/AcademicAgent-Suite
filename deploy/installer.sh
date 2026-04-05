#!/bin/bash

# Define colors for better logging
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[1/5] Checking permissions...${NC}"
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Error: Please run as root (use sudo).${NC}"
  exit 1
fi

echo -e "${GREEN}[2/5] Setting up GPG key and Repository...${NC}"
# Install dependencies for apt over HTTPS
apt update && apt install -y ca-certificates curl gnupg lsb-release

# Add GPG key from Tsinghua Mirror
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg

# Add Docker Source with Tsinghua Mirror
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

echo -e "${GREEN}[3/5] Installing Docker Engine...${NC}"
apt update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo -e "${GREEN}[4/5] Configuring Docker Daemon (Registry Mirror)...${NC}"
mkdir -p /etc/docker
cat <<EOF > /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
EOF

echo -e "${GREEN}[5/5] Restarting Docker service...${NC}"
systemctl daemon-reload
systemctl restart docker

# Final check
if systemctl is-active --quiet docker; then
    echo -e "${GREEN}Success: Docker has been installed and started.${NC}"
    docker --version
else
    echo -e "${RED}Error: Docker service failed to start.${NC}"
    exit 1
fi