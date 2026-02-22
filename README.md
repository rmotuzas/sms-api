# 📱 SMS API

HTTP REST sąsaja SMS žinučių siuntimui per **ZTE WCDMA** modemą (USB → Linux VPS).

## Funkcijos

- 🔐 **Token autentifikacija** — kiekvienas klientas gauna savo tokeną
- 📊 **Rate limiting** — konfiguruojami limitai (SMS/val, SMS/dieną) per tokeną
- 🌐 **Admin panel** — web sąsaja tokenų valdymui, SMS žurnalui, statistikai
- 🇱🇹 **Pilnas Unicode palaikymas** — lietuviškos raidės, emoji
- 📡 **Modemo statusas** — signalas, operatorius, tinklo tipas
- 📋 **SMS žurnalas** — visa istorija su filtrais

## Greitas startas

```bash
git clone https://github.com/YOUR_USER/sms-api.git
cd sms-api
sudo bash install.sh
```

Diegimo pabaigoje gausite admin slaptažodį ir API URL.

## API naudojimas

### Siųsti SMS

**Linux:**
```bash
curl -s -X POST https://sms-api.jusu-domenas.lt/api/sms/send -H "Authorization: Bearer JUSU_TOKENAS" -H "Content-Type: application/json" -d '{"to":"+37060000000","text":"Labas!"}'
```

**Windows CMD:**
```cmd
curl -s -X POST https://sms-api.jusu-domenas.lt/api/sms/send -H "Authorization: Bearer JUSU_TOKENAS" -H "Content-Type: application/json" -d "{\"to\":\"+37060000000\",\"text\":\"Labas!\"}"
```

### Endpoint'ai

| Metodas | URL | Aprašymas |
|---|---|---|
| `POST` | `/api/sms/send` | Siųsti SMS |
| `GET` | `/api/sms/status` | Modemo statusas |
| `GET` | `/api/sms/stats` | Naudojimo statistika |
| `GET` | `/health` | Serverio veikimas |
| `GET` | `/admin` | Admin panel |

### Atsakymų pavyzdžiai

```json
// Sėkmingas siuntimas
{ "success": true, "message": "SMS sent successfully", "to": "+37060000000", "length": 6 }

// Klaida
{ "error": "Invalid or expired token" }
{ "error": "Hourly limit exceeded (5/5)" }
```

## Admin panel

Pasiekiamas per `/admin`. Funkcijos:

- 📊 Dashboard su grafikais (SMS per 7 dienas)
- 🔑 Tokenų sąrašas: sukurti, išjungti, ištrinti
- 📋 SMS žurnalas su filtrais
- 📡 Modemo statusas + greitas SMS testas

## Reikalavimai

- Ubuntu 20.04+ / Debian 11+
- Python 3.8+
- ZTE WCDMA modemas (HTTP API per `192.168.0.1`)

## Dokumentacija

Žr. [`INSTALL.md`](INSTALL.md) — detalios diegimo instrukcijos.  
PDF dokumentacija klientams: [`docs/sms-api-dokumentacija.pdf`](docs/sms-api-dokumentacija.pdf)

## Projekto struktūra

```
sms-api/
├── app.py                  ← Flask programa (API + admin)
├── manage-tokens.py        ← CLI tokenų valdymas
├── requirements.txt        ← Python priklausomybės
├── install.sh              ← Automatinis diegimo skriptas
├── templates/              ← Admin panel HTML šablonai
├── systemd/
│   └── sms-api.service     ← systemd servisas
├── docs/
│   └── sms-api-dokumentacija.pdf
├── INSTALL.md              ← Diegimo instrukcija
└── README.md
```

## Licencija

Vidiniam naudojimui.
