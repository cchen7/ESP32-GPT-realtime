# Deploying the bridge on Debian

Target: the Debian host on the home LAN (gateway). Bridge runs as a
`systemctl --user` unit so it never touches system services.

## One-time setup

```bash
# 1. Push code from the Mac dev box (run from gpt-assistant/bridge/).
rsync -av --delete --exclude .venv --exclude '.env*' --exclude __pycache__ \
    ./ debian:~/work/gpt-assistant-bridge/

# 2. SSH in and install.
ssh debian
cd ~/work/gpt-assistant-bridge
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. Drop in service-principal credentials (Debian has no `az` cli).
#    Use the same SP as gpt-realtime2-demo, or rotate via ./rotate_secret.sh first.
cp .env.example .env
$EDITOR .env   # fill AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET

# 4. Install the user-mode systemd unit.
mkdir -p ~/.config/systemd/user
cp deploy/gpt-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gpt-bridge

# 5. Enable lingering so the unit keeps running after you log out.
loginctl enable-linger $USER   # (requires sudo on some distros)

# 6. Verify.
systemctl --user status gpt-bridge --no-pager
journalctl --user -u gpt-bridge -n 40 --no-pager
ss -tln | grep 8765
```

## From a device's point of view

After step 4, the bridge listens on `ws://<lan-ip>:8765`. Devices on the LAN
should resolve their default gateway and connect there:

```c
// firmware pseudo-code
esp_netif_ip_info_t ip;
esp_netif_get_ip_info(netif, &ip);
char ws_url[64];
snprintf(ws_url, sizeof ws_url, "ws://" IPSTR ":8765", IP2STR(&ip.gw));
```

## Known quirks

- **Stdout buffering**: `python -m bridge.server` would otherwise buffer log
  lines. The bridge calls `sys.stdout.reconfigure(line_buffering=True)` on
  start, and the unit file passes `python -u` for belt-and-braces.
- **Mac dev box behind a transparent HTTP proxy** (ClashX / Surge): the
  Python `websockets` client honors `HTTPS_PROXY`. Set
  `NO_PROXY=127.0.0.1,localhost,<your-lan-gateway-ip>` before running the test
  client or the bridge will see EOF on every connection.
- **Azure auth fallback chain** (Mac): `DefaultAzureCredential` tries SP env
  first, then `az login`. If `az` cached tokens are older than ~90 days you
  must `az login` again or the credential chain errors with AADSTS700082.
- **Conditional Access** may block service-principal logins from unknown IPs
  (AADSTS53003). On Debian (stable LAN IP, no `az`) we use SP unconditionally;
  if CA blocks the SP, ask the tenant admin to allow it for this app id.

## Updating the bridge

```bash
# from the Mac
rsync -av --delete --exclude .venv --exclude '.env*' --exclude __pycache__ \
    ./ debian:~/work/gpt-assistant-bridge/
ssh debian 'systemctl --user restart gpt-bridge && journalctl --user -u gpt-bridge -n 20 --no-pager'
```
