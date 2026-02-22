# SMS API — Diegimo instrukcija administratoriui

## Reikalavimai

| | |
|---|---|
| **OS** | Ubuntu 20.04+ arba Debian 11+ |
| **Python** | 3.8 arba naujesnė |
| **Modemas** | ZTE WCDMA (HTTP API per 192.168.0.1) |
| **Prieiga** | root arba sudo |

---

## 1. Modemo konfigūracija

Prieš diegdami SMS API — įsitikinkite, kad ZTE modemas pasiekiamas:

```bash
curl http://192.168.0.1/goform/goform_get_cmd_process?cmd=modem_main_state
```

**Turėtumėte gauti JSON atsakymą**, pvz.: `{"modem_main_state":"modem_init_complete"}`

### Jei modemas nepasiekiamas:

ZTE WCDMA modemą prisijungus per USB reikia sukonfigūruoti tinklo sąsają:

```bash
# Raskite tinklo sąsają
ip link show | grep enx

# Įjunkite ir priskirkite IP
ip link set enx344b50000000 up
ip addr add 192.168.0.100/24 dev enx344b50000000
```

### Auto-start modemo tinklui (`/etc/systemd/system/zte-modem-network.service`):

```ini
[Unit]
Description=ZTE Modem Network Setup
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/ip link set enx344b50000000 up
ExecStart=/sbin/ip addr add 192.168.0.100/24 dev enx344b50000000

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now zte-modem-network.service
```

> **Pastaba:** pakeiskite `enx344b50000000` į savo sąsajos pavadinimą.

---

## 2. Automatinis diegimas (rekomenduojama)

```bash
# Atsisiųskite projektą
git clone https://github.com/YOUR_USER/sms-api.git
cd sms-api

# Paleiskite diegimo skriptą
sudo bash install.sh
```

Skriptas automatiškai:
- Įdiegia Python3 ir pip
- Sukuria `/opt/sms-api/` direktoriją
- Įdiegia Python paketus (Flask)
- Sukuria ir paleidžia systemd servisą
- Sugeneruoja admin slaptažodį

---

## 3. Rankinis diegimas (žingsnis po žingsnio)

### 3.1 Python priklausomybės

```bash
apt-get update && apt-get install -y python3 python3-pip
pip3 install -r requirements.txt
```

### 3.2 Failų kopijavimas

```bash
mkdir -p /opt/sms-api/templates
cp app.py manage-tokens.py requirements.txt /opt/sms-api/
cp templates/*.html /opt/sms-api/templates/
chmod +x /opt/sms-api/app.py /opt/sms-api/manage-tokens.py
```

### 3.3 Systemd servisas

```bash
cp systemd/sms-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable sms-api
systemctl start sms-api
```

### 3.4 Patikrinimas

```bash
systemctl status sms-api
curl http://localhost:5000/health
```

---

## 4. Po diegimo

### Admin slaptažodis

Automatiškai sugeneruojamas pirmą kartą:

```bash
cat /opt/sms-api/admin.conf
```

Admin panel pasiekiamas: `http://SERVERIO_IP:5000/admin`

### Tokenų valdymas

```bash
cd /opt/sms-api

# Sukurti naują tokeną
python3 manage-tokens.py create "Projekto pavadinimas"

# Peržiūrėti visus tokenus
python3 manage-tokens.py list

# Atšaukti tokeną (pagal ID)
python3 manage-tokens.py revoke 2

# Statistika
python3 manage-tokens.py stats
```

---

## 5. Ugunsiena (firewall)

```bash
# UFW (Ubuntu)
ufw allow 5000/tcp

# arba iptables
iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
```

> **Rekomenduojama:** naudokite reverse proxy (Nginx / NPM) su HTTPS ir
> neatidarinėkite 5000 porto tiesiai į internetą.

---

## 6. Nginx Proxy Manager (NPM) konfigūracija

Jei naudojate NPM:

| Laukas | Reikšmė |
|---|---|
| **Domain** | sms-api.jusu-domenas.lt |
| **Scheme** | http |
| **Forward Host** | 192.168.x.x (serverio IP) |
| **Forward Port** | 5000 |
| **SSL** | Let's Encrypt (rekomenduojama) |

---

## 7. Servisų komandos

```bash
# Statusas
systemctl status sms-api

# Perkraukite po konfigūracijos pakeitimų
systemctl restart sms-api

# Žurnalai (realiu laiku)
journalctl -u sms-api -f

# SMS API log failas
tail -f /var/log/sms-api.log
```

---

## 8. Šalinimas

```bash
sudo bash install.sh uninstall
```

---

## Failų struktūra

```
/opt/sms-api/
├── app.py              ← Pagrindinis Flask servisas
├── manage-tokens.py    ← Tokenų valdymo įrankis
├── requirements.txt    ← Python priklausomybės
├── tokens.db           ← SQLite duomenų bazė (tokenai + žurnalas)
├── admin.conf          ← Admin slaptažodis (chmod 600)
├── .secret_key         ← Flask sesijų raktas (chmod 600)
├── templates/
│   ├── admin_base.html
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── admin_tokens.html
│   ├── admin_logs.html
│   └── admin_modem.html
```

---

## Dažniausios klaidos

| Klaida | Priežastis | Sprendimas |
|---|---|---|
| `Connection refused` (192.168.0.1) | Modemas DOWN | `ip link set enxXXX up && ip addr add 192.168.0.100/24 dev enxXXX` |
| `Modem error: {'result': 'failure'}` | Netinkamas užklausos formatas | Patikrinkite `sms_time=` lauką ir `Referer` antraštę |
| `Invalid or expired token` | Tokenas neteisingas | Tokenas turi būti `Authorization: Bearer` antraštėje |
| `400 Bad Request` iš Windows | JSON su single quotes | Windows CMD naudokite `\"` vietoj `'` |
| Servisas nepaleidžiamas | Flask neįdiegtas | `pip3 install flask werkzeug` |
