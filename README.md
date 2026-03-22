##Happy Plant:

*Smart irrigation that measures its own climate impact.*

Happy Plant turns urban green spaces into measurable climate actions. Instead of just watering smarter, we track exactly how much water is saved, how much CO₂ plants absorb, and what contribution each green space makes — giving cities and communities real numbers, not just good intentions.

---

## Core Features

*Next Watering* — Sensor-driven scheduling that tells you when, how much, and why. Rain predicted? Watering shifts automatically, saving hundreds of liters per month.

*Plant Health* — Every plant gets a live health score (0–100) based on soil moisture, light, and environmental data. One glance shows what's thriving and what needs attention.

*Climate Impact* — The differentiator. We quantify water saved, CO₂ absorbed, and urban greening contribution. Not "we water smart" — but "here's the measurable climate effect."

---

## Two Products, One Platform

### 🏙️ City Dashboard — Urban Green Spaces
Web-based dashboard for managing parks and public green spaces. AI chat interface with n8n workflow integration, weekly statistics, care calendar, and real-time environment monitoring. Currently piloted at *Stadtpark Heilbronn* (roses & lavender).

### 🏢 Office Hardware — Smart Plant Sensor
ESP32-CAM based device you stick into any office plant. It automatically:
•⁠  ⁠*Identifies the plant* via camera + Plant.id API
•⁠  ⁠*Monitors soil moisture* in real-time (digital sensor)
•⁠  ⁠*Waters automatically* when soil is dry (pump control via transistor)
•⁠  ⁠*Shows status via LEDs* — green = healthy, red = needs water

The hardware runs autonomously in 15-second cycles: photograph → identify → measure → water if needed. No app required for basic operation, but connects to the Happy Plant dashboard for monitoring and analytics.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Dashboard | Single-file HTML/CSS/JS, DM Sans |
| AI Chat | n8n webhook workflows |
| Hardware | ESP32-CAM (AI Thinker), soil moisture sensor, relay/transistor pump control |
| Plant ID | Plant.id API v2 (camera → base64 → identify) |
| Firmware | Arduino/C++ (⁠ happyplant.ino ⁠) |

---

## Repository Structure


├── happy-plant-dashboard.html   # Web dashboard (runs in any browser)
├── happyplant.ino               # ESP32-CAM firmware (Arduino IDE)
└── README.md


---

## Getting Started

*Dashboard* — Open ⁠ happy-plant-dashboard.html ⁠ in any browser. No build step, no dependencies.

*Hardware* — Flash ⁠ happyplant.ino ⁠ to an ESP32-CAM (AI Thinker) via Arduino IDE. Set your WiFi credentials and Plant.id API key in the config section. Wire soil moisture sensor to GPIO14, pump transistor to GPIO4, LEDs to GPIO33/GPIO2.

---

## What's Next

Mobile app with push notifications · Multi-location management · Public climate dashboard for city reporting · Sensor data streaming to dashboard · Plant care recommendations based on species identification
