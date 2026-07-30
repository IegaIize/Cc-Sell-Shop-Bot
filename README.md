# 💳 Card Shop Bot

A Telegram bot for purchasing virtual card packages with balance system, BIN lookup, and refund support.

## 🚀 Features

- **3 Card Packages**: Economic (20 cards/$1), Fast (50 cards/$3), Custom (70 cards/$5)
- **Balance System**: Deposit with Stars, promo codes, transaction history
- **BIN Lookup**: Real-time card information via API
- **Refund System**: Report non-working cards for admin approval
- **Multi-language**: Turkish & English support
- **Admin Panel**: User management, statistics, announcements
- **Spam Protection**: Rate limiting for commands

---

## 📦 Installation

```bash
# Clone repository
git clone <repo-url>
cd card-shop-bot

# Install dependencies
pip install -r requirements.txt

# Configure bot token in bot.py
# BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
# ADMIN_ID = YOUR_TELEGRAM_ID

# Run bot
python bot.py

-

Command Description (user commands)

/start Start bot & language selection
/help Show help guide
/price View price list
/contact Support contact info
/profile Account information & balance
/buy Open purchase menu
/fast Quick buy Fast Package (50 cards/$3)
/custom <BIN> Buy Custom Package with BIN (70 cards/$5)
/economic Buy Economic Package (20 cards/$1)
/mycards View purchased cards history

-

Command Description (admin commands)

/admin Show all admin commands
/filelist List all card files
/filedelete <number> Delete card file by number
/upload Upload card file (send .txt after command)
/add Add cards via text message
/stats Global statistics
/giveaway <amount> Give balance to all users
/announce <message> Send announcement to all users
/ban <id> Ban a user
/unban <id> Unban a user
/createcode <amount> Create promo code

-

Pricing

Package Price Cards Feature
💎 Economic $1.00 20 Mixed banks
⚡ Fast $3.00 50 Mixed banks
🎯 Custom $5.00 70 BIN selection

-

card-shop-bot/
├── bot.py                 # Main bot code
├── requirements.txt       # Dependencies
├── README.md              # Documentation
├── cards_data/            # Card files directory
│   └── cards_*.txt        # Card data files
├── users.json             # User database
├── promo_codes.json       # Promo codes
├── banned_users.json      # Banned users list
└── current_cards.txt      # All cards merged

code by telegram @IegaIize 
