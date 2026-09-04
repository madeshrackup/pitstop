# Pitstop online server — setup in plain English

This is the **always-on** path: a small cloud computer that stays on even when your Mac is off. Friends only need Dolphin + your Pitstop launcher.

---

## What you’re building (one sentence)

A private Mario Kart “online lobby computer” in the cloud, with a free web address, that Pitstop connects to instead of Nintendo / public WiiLink.

---

## If Oracle verification fails (read this first)

Truly free always-on VPS options are rare. Realistic choices:

| Option | Cost | Notes |
|--------|------|--------|
| **Oracle Always Free** | $0 | Best free specs; signup/verify often fails |
| **Google Cloud e2-micro** | $0 forever (US regions) | Tiny (1 GB RAM) — tight for Postgres + WWFC; also needs card verify |
| **Hetzner Cloud** (recommended if Oracle fails) | ~€4–5 / month | Real VPS, easy signup, UDP works, closest to “just works” |
| **DigitalOcean / Vultr** | ~$4–6 / month | Same idea as Hetzner |
| **Your Mac + Tailscale** | $0 | Only while your Mac is on |

**Recommendation:** if Oracle won’t verify, use **Hetzner** (~cup of coffee per month) for 3 friends. Same Docker files work; only the “create VM + open ports” steps change. If you already have **Google Cloud** trial credit, use that first (steps below).

### Google Cloud quick path (you are here)

You’re already signed in with free-trial credit. Do this in order:

#### G1. Create the VM
1. Top search bar → type **Compute Engine** → open **Compute Engine**
2. If it asks to enable the API, click **Enable** and wait ~1 minute
3. Left menu → **VM instances** → **Create instance**
4. Fill in:
   - **Name:** `pitstop`
   - **Region:** `europe-west2` (London) — best for UK; uses trial credit  
     (After the trial, the tiny always-free machine only exists in US regions.)
   - **Machine type:** **e2-small** (2 GB RAM) — don’t pick e2-micro yet; 1 GB is too tight
   - **Boot disk:** change → **Ubuntu** → **Ubuntu 24.04 LTS** → size **20 GB** → Select
   - **Firewall:** tick **Allow HTTP traffic** and **Allow HTTPS traffic**
5. Expand **Advanced options → Networking**
   - Under **Network interfaces**, confirm it has **External IPv4** (Ephemeral is fine)
6. Expand **Security** (or “SSH Keys” depending on UI)
   - Paste your Mac SSH public key (see G3 if you don’t have one)
7. Click **Create** → wait until status is green / Running
8. Copy the **External IP** from the VM list — keep it for DuckDNS

#### G2. Open game ports (VPC firewall)
1. Search → **VPC network** → **Firewall**
2. **Create firewall rule** once for TCP, once for UDP (or combine if the UI lets you):

**Rule A — TCP**
- Name: `pitstop-tcp`
- Direction: Ingress
- Targets: All instances in the network (or tag `pitstop` if you set one)
- Source IPv4 ranges: `0.0.0.0/0`
- Protocols/ports: Specified → TCP →  
  `22,80,443,28910,29900,29901,29920,29997`
- Create

**Rule B — UDP**
- Name: `pitstop-udp`
- Same as above, but UDP → `27900,27901`
- Create

#### G3. SSH key on your Mac (if needed)
In Terminal:
```bash
ls ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub 2>/dev/null
# if none:
ssh-keygen -t ed25519 -C "pitstop"
cat ~/.ssh/id_ed25519.pub
```
Paste that whole line into the VM’s SSH keys field (username before `@` becomes the Linux login, or use `madesh` / your Google username).

#### G4. Log in
```bash
ssh YOUR_USERNAME@YOUR_EXTERNAL_IP
```
(Google often uses the username from the SSH key comment/prefix. If unsure, use **SSH → View gcloud command** on the VM row, or the browser SSH button once.)

Then continue from **Part B (DuckDNS)** in this file — same as Oracle from there.

---

### Hetzner quick path (paid but simple)
1. Sign up at [hetzner.com/cloud](https://www.hetzner.com/cloud)
2. Create a project → **Add server**
3. Location near you (e.g. Falkenstein / Nuremberg / Helsinki)
4. Image: **Ubuntu 24.04**
5. Type: cheapest shared **CX22** or **CAX11** (ARM) is fine
6. Add your SSH key → Create
7. Copy the public IP
8. Open firewall in Hetzner Cloud Firewall (or `ufw` on the box) for the same ports listed in Part A4 below
9. Continue from **Part B (DuckDNS)** — same as Oracle from there

---

## Part A — Free cloud computer (Oracle)

### A1. Make an account
1. Open [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)
2. Click **Start for free**
3. Sign up with email + phone
4. They usually ask for a **credit/debit card** to prove you’re real — stay on **Always Free** shapes and you should not be charged for this setup
5. Pick a home region close to you (e.g. UK / Germany / US) and finish signup

### A2. Create the computer (VM)
1. In the Oracle dashboard, go to **Compute → Instances → Create instance**
2. Name it something like `pitstop`
3. **Image:** Canonical Ubuntu 22.04 or 24.04
4. **Shape:**
   - Prefer **Ampere** (ARM) → `VM.Standard.A1.Flex` with about **2 OCPUs** and **12 GB RAM**
   - If it says **Out of capacity**, try again later, try another availability domain, or use the tiny **AMD Micro** shape instead
5. **Networking:** make sure it gets a **public IP** (not private-only)
6. **SSH keys:** add your Mac’s public key  
   - On your Mac Terminal: `cat ~/.ssh/id_ed25519.pub` (or `id_rsa.pub`)  
   - If you don’t have one: `ssh-keygen -t ed25519` then paste the `.pub` file contents into Oracle
7. Click **Create**

### A3. Note your public IP
On the instance page, copy the **Public IP address** (looks like `132.145.x.x`). Keep it handy.

### A4. Open the “doors” (security list)
Oracle blocks almost everything by default. Open these inbound rules on the VCN **Default Security List** (Networking → Virtual Cloud Networks → your VCN → Security Lists):

| Type | Ports | Why |
|------|-------|-----|
| TCP | 22 | SSH (you logging in) |
| TCP | 80, 443 | Login / web-style game traffic |
| TCP | 28910, 29900, 29901, 29920, 29997 | GameSpy / payload |
| UDP | 27900, 27901 | Matchmaking / NAT helper |

Source: `0.0.0.0/0` (anywhere) for a private friend server with 3 people is fine.

### A5. Log in from your Mac
```bash
ssh ubuntu@YOUR_PUBLIC_IP
```
(If the default user isn’t `ubuntu`, Oracle’s instance page will say which username to use.)

### A6. Open the same doors inside Linux
Oracle’s Ubuntu image often has a second firewall. On the VM:

```bash
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 28910 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 29900 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 29901 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 29920 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 29997 -j ACCEPT
sudo iptables -I INPUT -p udp --dport 27900 -j ACCEPT
sudo iptables -I INPUT -p udp --dport 27901 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get install -y iptables-persistent
```

---

## Part B — Free web name (DuckDNS)

Games need a **name**, not just an IP.

1. Open [duckdns.org](https://www.duckdns.org) and sign in (Google/GitHub is fine)
2. Create a subdomain, e.g. `pitstop-mkw` → `pitstop-mkw.duckdns.org`
3. Set its IP to your Oracle **public IP**
4. Tell me that full name (example: `pitstop-mkw.duckdns.org`) — we bake it into the Pitstop game patch

---

## Part C — Install Docker on the VM

Still SSH’d into the server:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in so docker works without sudo
exit
```

SSH back in, then:

```bash
docker version
```

---

## Part D — We deploy Pitstop’s server files

Once you have:
- SSH working
- public IP
- DuckDNS name

…say so in chat. We’ll copy the `server/` folder up, build the client patch for your DuckDNS name, and start the stack with:

```bash
cd server
./deploy.sh
```

---

## Part E — Friends

They only need:
1. Dolphin
2. Their own Mario Kart Wii dump
3. Your Pitstop launcher (same pack you use)

No Oracle account, no NAND, no Wiimmfi wait.

---

## Troubleshooting (short)

| Symptom | Likely fix |
|---------|------------|
| Can’t create ARM VM | Retry later / other AD / use AMD Micro |
| SSH works, game can’t connect | Security list **and** iptables both need the ports |
| Error about payload / 20912 | Client patch domain must match the server payload build |
| “Additional setup / WiiLink on Dolphin” | You’re still on **public** WiiLink — private server must have `allowDefaultDolphinKeys=true` (already set in our config) |

---

## Cost reminder

Stay on **Always Free** shapes only. Don’t upgrade to paid shapes unless you mean to.
