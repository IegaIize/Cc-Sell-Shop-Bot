import os
import json
import random
import string
import time
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# --- CONFIGURATION ---
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 1234567890
USERS_FILE = "users.json"
PROMO_CODES_FILE = "promo_codes.json"
BANNED_USERS_FILE = "banned_users.json"
CARDS_DIR = "cards_data"
CURRENT_CARDS_FILE = "current_cards.txt"

# Spam protection
SPAM_COUNTER = {}
SPAM_LIMIT = 5
SPAM_TIME_WINDOW = 1
SPAM_BAN_TIME = 15

# --- STATES ---
LANGUAGE, MAIN_MENU, BUY_CARD, BIN_INPUT, PROMO_INPUT, BIN_QUERY, ADMIN_ADD_CARDS, DEPOSIT_AMOUNT = range(8)

# Card prices and quantities
CARD_PRICES = {
    'economic': {
        'price': 1.0,
        'count': 20,
        'name': 'Economic',
        'description': 'Budget friendly, 20 cards'
    },
    'fast': {
        'price': 3.0,
        'count': 50,
        'name': 'Fast',
        'description': 'Medium quality, 50 cards'
    },
    'custom': {
        'price': 5.0,
        'count': 70,
        'name': 'Custom',
        'description': 'Premium quality, 70 cards + BIN selection'
    }
}

# --- FILE MANAGEMENT ---
def init_files():
    """Create necessary files"""
    if not os.path.exists(CARDS_DIR):
        os.makedirs(CARDS_DIR)
    
    if not os.path.exists(CURRENT_CARDS_FILE):
        with open(CURRENT_CARDS_FILE, 'w', encoding='utf-8') as f:
            pass
    
    if not os.path.exists(BANNED_USERS_FILE):
        with open(BANNED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def get_card_files():
    """List all card files"""
    files = []
    if os.path.exists(CARDS_DIR):
        for filename in os.listdir(CARDS_DIR):
            if filename.endswith('.txt'):
                filepath = os.path.join(CARDS_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    card_count = sum(1 for line in f if line.strip())
                files.append({
                    'name': filename,
                    'path': filepath,
                    'cards': card_count
                })
    return files

def merge_all_cards():
    """Merge all card files"""
    all_cards = []
    files = get_card_files()
    for file_info in files:
        with open(file_info['path'], 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    all_cards.append(line.strip())
    
    with open(CURRENT_CARDS_FILE, 'w', encoding='utf-8') as f:
        for card in all_cards:
            f.write(card + '\n')
    
    return all_cards

def load_cards():
    """Load all cards (merged)"""
    return merge_all_cards()

def add_cards_to_file(card_list):
    """Add new cards to file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"cards_{timestamp}.txt"
    filepath = os.path.join(CARDS_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for card in card_list:
            f.write(card + '\n')
    
    merge_all_cards()
    
    return filename, len(card_list)

# --- SPAM PROTECTION ---
def is_spamming(user_id: int) -> bool:
    """Check if user is spamming"""
    now = time.time()
    if user_id not in SPAM_COUNTER:
        SPAM_COUNTER[user_id] = {'count': 1, 'first_time': now, 'banned_until': 0}
        return False
    
    user_data = SPAM_COUNTER[user_id]
    
    if user_data['banned_until'] > now:
        return True
    
    if now - user_data['first_time'] <= SPAM_TIME_WINDOW:
        user_data['count'] += 1
        if user_data['count'] >= SPAM_LIMIT:
            user_data['banned_until'] = now + SPAM_BAN_TIME
            user_data['count'] = 0
            return True
    else:
        user_data['count'] = 1
        user_data['first_time'] = now
    
    return False

# --- BAN MANAGEMENT ---
def load_banned_users():
    """Load banned users"""
    try:
        with open(BANNED_USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_banned_users(banned_users):
    """Save banned users"""
    with open(BANNED_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(banned_users, f, ensure_ascii=False, indent=2)

def is_user_banned(user_id: int) -> bool:
    """Check if user is banned"""
    banned_users = load_banned_users()
    return user_id in banned_users

def ban_user(user_id: int):
    """Ban a user"""
    banned_users = load_banned_users()
    if user_id not in banned_users:
        banned_users.append(user_id)
        save_banned_users(banned_users)

def unban_user(user_id: int):
    """Unban a user"""
    banned_users = load_banned_users()
    if user_id in banned_users:
        banned_users.remove(user_id)
        save_banned_users(banned_users)

# --- BIN LOOKUP API ---
def get_bin_info(bin_number):
    """Get card information from BIN number"""
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin_number}", headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept-Version': '3'
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            card_type = data.get('type', 'Unknown')
            if card_type:
                card_type = card_type.capitalize()
            else:
                card_type = 'Credit'
            
            brand = data.get('scheme', 'Unknown')
            if brand:
                brand = brand.upper()
            else:
                brand = 'VISA'
            
            bank = data.get('bank', {})
            bank_name = bank.get('name', 'Unknown Bank')
            
            country = data.get('country', {})
            country_name = country.get('name', 'Unknown')
            country_code = country.get('alpha2', '')
            
            card_level = 'Standard'
            if data.get('prepaid'):
                card_level = 'Prepaid'
            
            return {
                'type': card_type,
                'brand': brand,
                'bank': bank_name,
                'country': country_name,
                'country_code': country_code,
                'level': card_level,
                'valid': True
            }
        else:
            return get_default_bin_info(bin_number)
            
    except Exception as e:
        print(f"BIN API Error: {e}")
        return get_default_bin_info(bin_number)

def get_default_bin_info(bin_number):
    """Default BIN info when API fails"""
    first_digit = bin_number[0] if bin_number else '4'
    
    if first_digit == '4':
        brand = 'VISA'
    elif first_digit == '5':
        brand = 'MasterCard'
    elif first_digit == '3':
        brand = 'American Express'
    else:
        brand = 'VISA'
    
    if bin_number.startswith(('4543', '5502', '5526', '5530')):
        bank = 'YAPI VE KREDI BANKASI A.S.'
        country = 'TURKEY'
        country_code = 'TR'
    elif bin_number.startswith(('4282', '4938', '5406', '5433')):
        bank = 'AKBANK T.A.S.'
        country = 'TURKEY'
        country_code = 'TR'
    elif bin_number.startswith(('4029', '4163', '5298', '5311')):
        bank = 'TURKIYE IS BANKASI A.S.'
        country = 'TURKEY'
        country_code = 'TR'
    elif bin_number.startswith(('4508', '4532', '4553', '4931')):
        bank = 'GARANTI BANKASI A.S.'
        country = 'TURKEY'
        country_code = 'TR'
    else:
        bank = 'YAPI VE KREDI BANKASI A.S.'
        country = 'TURKEY'
        country_code = 'TR'
    
    return {
        'type': 'Credit',
        'brand': brand,
        'bank': bank,
        'country': country,
        'country_code': country_code,
        'level': 'SIGNATURE',
        'valid': False
    }

# --- TEXT MESSAGES ---
TEXTS = {
    'welcome': "🛡️ <b>Security Check</b>\n\n🌍 Select your language to continue:",
    'lang_selected': "✅ <b>Success!</b>",
    'welcome_back': "🔥 <b>Welcome Back, {username}!</b>\n\n"
                   "🚀 <b>Digital Card Platform</b> active\n\n"
                   "🎯 <b>Our Services:</b>\n"
                   "• 💎 <b>Economic Cards</b> - 20 cards for $1\n"
                   "• ⚡ <b>Fast Cards</b> - 50 cards for $3\n"
                   "• 🎯 <b>Custom Cards</b> - 70 cards for $5\n\n"
                   "📦 <b>Stock Status:</b>\n"
                   "• Available: <code>250K+</code> cards\n\n"
                   "👇 <b>Use menu to start</b>",
    'main_menu': "🎮 <b>Control Panel</b>",
    'price_list': "💰 <b>PRICE LIST</b>\n\n"
                 "━━━━━━━━━━━━━━━━━━━━━\n"
                 "💎 <b>Economic Card Package</b>\n"
                 "• Price: <code>$1</code>\n"
                 "• Quantity: <b>20 cards</b>\n"
                 "• Delivery: <b>Instant</b>\n"
                 "• Feature: Mixed banks\n\n"
                 "⚡ <b>Fast Card Package</b>\n"
                 "• Price: <code>$3</code>\n"
                 "• Quantity: <b>50 cards</b>\n"
                 "• Delivery: <b>Instant</b>\n"
                 "• Feature: Mixed banks\n\n"
                 "🎯 <b>Custom Card Package</b>\n"
                 "• Price: <code>$5</code>\n"
                 "• Quantity: <b>70 cards</b>\n"
                 "• Delivery: <b>Instant</b>\n"
                 "• Feature: BIN selection\n\n"
                 "📊 <b>Inventory:</b>\n"
                 "• Total: <code>250K+</code>\n"
                 "• Active: <code>50K+</code>\n"
                 "• Premium: <code>5K+</code>\n\n"
                 "🎖️ VIP status above <code>$1000</code>",
    'profile': "👨‍💼 <b>ACCOUNT INFO</b>\n"
              "━━━━━━━━━━━━━━━━━━━━━\n\n"
              "🆔 <b>ID:</b> <code>{user_id}</code>\n"
              "👤 <b>User:</b> @{username}\n"
              "📅 <b>Joined:</b> {join_date}\n\n"
              "💳 <b>FINANCIAL STATUS</b>\n"
              "━━━━━━━━━━━━━━━━━━━━━\n"
              "• <b>Balance:</b> <code>${balance:.2f}</code>\n"
              "• <b>Month Spend:</b> <code>${month_spent:.2f}</code>\n"
              "• <b>Month Cards:</b> <code>{month_cards} pcs</code>\n"
              "• <b>Total:</b> <code>${total_spent:.2f}</code>",
    'help': "📚 <b>USER GUIDE</b>\n\n"
           "🎮 <b>Basic Commands:</b>\n"
           "• /start - Start\n"
           "• /help - Help\n"
           "• /price - Prices\n"
           "• /contact - Support\n"
           "• /profile - Account\n\n"
           "🛒 <b>Purchase:</b>\n"
           "• /buy - Buy\n"
           "• /fast - Fast cards (50 pcs)\n"
           "• /custom - Custom cards (70 pcs)\n"
           "• /economic - Economic cards (20 pcs)\n"
           "• /mycards - History",
    'contact': "☎️ <b>SUPPORT CENTER</b>\n\n"
              "🕐 <b>Hours:</b>\n"
              "• Always active\n\n"
              "📲 <b>Contact:</b>\n"
              "• @yourname\n\n"
              "⏰ <b>Response:</b>\n"
              "• Within 30 mins\n\n"
              "💡 <b>Note:</b>\n"
              "• Transaction ID for issues\n"
              "• Screenshot helpful\n\n"
              "🙏 <b>Thank You!</b>",
    'buy_menu': "🛍️ <b>PURCHASE</b>\n\n"
               "👇 <b>Select card type:</b>\n\n"
               "• <b>Economic Cards</b> - 20 cards for $1\n"
               "• <b>Fast Cards</b> - 50 cards for $3\n"
               "• <b>Custom Cards</b> - 70 cards for $5",
    'bin_purchase': "🎯 <b>CUSTOM CARD BUY</b>\n\n"
                   "🔢 Type your BIN number:",
    'insufficient_balance': "⚠️ <b>NO BALANCE</b>\n\n"
                           "Required: <code>${required:.2f}</code>\n"
                           "Current: <code>${balance:.2f}</code>\n\n"
                           "💳 Top up first",
    'promo_input': "🎟️ <b>USE CODE</b>\n\n"
                  "⌨️ Enter your code:\n\n"
                  "ℹ️ <b>Info:</b>\n"
                  "• One-time use\n"
                  "• Case insensitive\n"
                  "• May expire\n\n"
                  "📝 Type and send",
    'promo_success': "✅ <b>Code used!</b>\n\n<code>${amount:.2f}</code> added to your account.",
    'promo_invalid': "❌ <b>Invalid code!</b>\n\nTry again.",
    'bin_query': "🔍 <b>STOCK CHECK</b>\n\n"
                "Type BIN number to search:",
    'available_bins': "📋 <b>AVAILABLE BINS</b>\n\n"
                    "👇 <b>Select card type:</b>\n\n"
                    "💳 <b>Normal</b> - Standard\n"
                    "🏦 <b>Economic</b> - Bank",
    'my_cards': "📜 <b>YOUR CARDS:</b>\n\n",
    'no_cards': "📭 <b>No cards yet!</b>",
    'transactions': "📊 <b>TRANSACTIONS:</b>\n\n",
    'no_transactions': "📭 <b>No transactions!</b>",
    'balance_history': "💰 <b>BALANCE HISTORY:</b>\n\n",
    'no_balance_history': "📭 <b>No history!</b>",
    'back_to_menu': "🔙 Main Menu",
    'select_option': "👇 Make selection:",
    'card_feedback_request': "👇 <b>Report card status:</b>",
    'card_report_received': "📢 <b>Card complaint received!</b>\n\n"
                           "User: {user}\n"
                           "Card: {card}\n\n"
                           "Decide:",
    'refund_approved': "✅ <b>Refund approved!</b>\n\n"
                      "<code>${amount:.2f}</code> refunded to your account.",
    'refund_rejected': "❌ <b>Refund rejected!</b>\n\n"
                      "Your card is working.",
    'card_declined': "❌ <b>Card not working!</b>\n\n"
                    "Your refund request sent to admin.",
    'banned': "🚫 <b>YOUR ACCOUNT IS BANNED!</b>\n\n"
              "You cannot use the bot.",
    'spam_warning': "⚠️ <b>TOO MANY REQUESTS!</b>\n\n"
                    "Please wait 15 seconds.",
    'deposit_amount': "💰 <b>DEPOSIT</b>\n\n"
                     "How much balance do you want to add?",
    'deposit_5': "5 USD PURCHASE ✅\n\n"
                "Send <b>25 Stars</b> to <b>@legaIize</b> and return to the bot to click <b>Sent</b> button.",
    'deposit_10': "10 USD PURCHASE ✅\n\n"
                 "Send <b>50 Stars</b> to <b>@legaIize</b> and return to the bot to click <b>Sent</b> button.",
    'deposit_20': "20 USD PURCHASE ✅\n\n"
                 "Send <b>100 Stars</b> to <b>@legaIize</b> and return to the bot to click <b>Sent</b> button.",
    'deposit_50': "50 USD PURCHASE ✅\n\n"
                 "Send <b>250 Stars</b> to <b>@legaIize</b> and return to the bot to click <b>Sent</b> button.",
    'deposit_100': "100 USD PURCHASE ✅\n\n"
                  "Send <b>500 Stars</b> to <b>@legaIize</b> and return to the bot to click <b>Sent</b> button.",
    'deposit_confirm': "✅ <b>Payment request received!</b>\n\n"
                      "Waiting for admin approval...",
    'deposit_request_received': "💰 <b>DEPOSIT REQUEST RECEIVED!</b>\n\n"
                              "User: {user}\n"
                              "Amount: <code>${amount}</code>\n"
                              "Request ID: <code>{deposit_id}</code>\n\n"
                              "Decide:",
    'deposit_approved': "✅ <b>Deposit approved!</b>\n\n"
                       "<code>${amount}</code> added to your account.\n"
                       "New balance: <code>${new_balance:.2f}</code>",
    'deposit_rejected': "❌ <b>Deposit request rejected!</b>\n\n"
                       "Please try again later.",
    'not_enough_cards': "❌ <b>Not enough cards!</b>\n\n"
                       "Available: <code>{available}</code> cards\n"
                       "Required: <code>{required}</code> cards\n\n"
                       "Please contact admin.",
    'purchase_success': "✅ <b>Card Package Purchased!</b>\n\n"
                       "Below are <b>{count} cards</b>:",
    'no_bin_cards': "❌ <b>Not enough cards with this BIN!</b>\n\n"
                   "Required: <code>{required}</code> cards\n"
                   "Available: <code>{available}</code> cards"
}

# --- DATABASE FUNCTIONS ---
def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_promo_codes():
    try:
        with open(PROMO_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_promo_codes(codes):
    with open(PROMO_CODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)

# --- USER FUNCTIONS ---
def get_user_data(user_id: int):
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'language': 'en',
            'balance': 0.0,
            'join_date': date.today().strftime('%m/%d/%Y'),
            'month_spent': 0.0,
            'month_cards': 0,
            'total_spent': 0.0,
            'purchased_cards': [],
            'transactions': [],
            'balance_history': [],
            'has_seen_welcome': False,
            'username': None
        }
        save_users(users)
    return users[str(user_id)]

def update_user_data(user_id: int, data: dict):
    users = load_users()
    if str(user_id) in users:
        users[str(user_id)].update(data)
    else:
        users[str(user_id)] = data
    save_users(users)

def add_transaction(user_id: int, transaction_type: str, amount: float, description: str):
    user = get_user_data(user_id)
    transaction = {
        'date': datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
        'type': transaction_type,
        'amount': amount,
        'description': description
    }
    user['transactions'].append(transaction)
    update_user_data(user_id, user)

def add_balance_history(user_id: int, change: float, reason: str):
    user = get_user_data(user_id)
    history = {
        'date': datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
        'change': change,
        'reason': reason,
        'balance_after': user['balance'] + change
    }
    user['balance_history'].append(history)
    update_user_data(user_id, user)

# --- CARD REFUND SYSTEM ---
PENDING_REFUNDS = {}
PENDING_DEPOSITS = {}

def card_feedback_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Live", callback_data='card_live')],
        [InlineKeyboardButton("❌ DEC", callback_data='card_declined')]
    ])

def admin_refund_keyboard(refund_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve Refund", callback_data=f'refund_approve_{refund_id}'),
         InlineKeyboardButton("❌ Reject Refund", callback_data=f'refund_reject_{refund_id}')]
    ])

def purchase_confirm_keyboard(package_type):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Buy", callback_data=f'buy_{package_type}')],
        [InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_{package_type}')]
    ])

def deposit_amount_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 USD", callback_data='deposit_5'),
         InlineKeyboardButton("10 USD", callback_data='deposit_10')],
        [InlineKeyboardButton("20 USD", callback_data='deposit_20'),
         InlineKeyboardButton("50 USD", callback_data='deposit_50')],
        [InlineKeyboardButton("100 USD", callback_data='deposit_100')],
        [InlineKeyboardButton("🔙 Back", callback_data='cancel_deposit')]
    ])

def deposit_confirm_keyboard(deposit_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sent", callback_data=f'deposit_sent_{deposit_id}')],
        [InlineKeyboardButton("❌ Cancel", callback_data=f'deposit_cancel_{deposit_id}')]
    ])

def admin_deposit_keyboard(deposit_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f'deposit_approve_{deposit_id}'),
         InlineKeyboardButton("❌ Reject", callback_data=f'deposit_reject_{deposit_id}')]
    ])

# --- REPLY KEYBOARDS ---
def main_menu_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["💰 Prices", "👤 Account"],
        ["📚 Help", "☎️ Support"],
        ["🛍️ Buy", "💳 Balance"],
        ["🔍 Stock Check", "🎟️ Code"]
    ], resize_keyboard=True, one_time_keyboard=False)

def profile_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📜 My Cards", "📊 Transactions"],
        ["💰 History", "🌍 Language"],
        ["💳 Add Balance", "🔙 Main Menu"]
    ], resize_keyboard=True, one_time_keyboard=True)

def buy_menu_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["🎯 Buy Custom", "⚡ Buy Fast"],
        ["💎 Buy Economic"],
        ["🔍 Stock Check"],
        ["🔙 Main Menu"]
    ], resize_keyboard=True, one_time_keyboard=True)

def back_to_menu_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["🔙 Main Menu"]
    ], resize_keyboard=True, one_time_keyboard=True)

# --- INLINE KEYBOARDS ---
def language_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇹🇷 Turkish", callback_data='lang_tr'),
         InlineKeyboardButton("🇺🇸 English", callback_data='lang_en')]
    ])

def bin_type_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Normal", callback_data='view_credit_bins'),
         InlineKeyboardButton("🏦 Economic", callback_data='view_debit_bins')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_bin_query')]
    ])

# --- CARD PACKAGE SENDING FUNCTION ---
async def send_card_package_to_user(update, user_id, user_data, package_type, bin_num=None):
    """Send card package to user and update records"""
    package_info = CARD_PRICES[package_type]
    required_amount = package_info['price']
    card_count = package_info['count']
    
    if user_data['balance'] < required_amount:
        if hasattr(update, 'message'):
            await update.message.reply_text(
                TEXTS['insufficient_balance'].format(
                    required=required_amount,
                    balance=user_data['balance']
                ),
                reply_markup=back_to_menu_reply_keyboard(),
                parse_mode='HTML'
            )
        else:
            await update.edit_message_text(
                TEXTS['insufficient_balance'].format(
                    required=required_amount,
                    balance=user_data['balance']
                ),
                parse_mode='HTML'
            )
        return False
    
    all_cards = load_cards()
    
    filtered_cards = []
    if bin_num:
        for card in all_cards:
            if card.startswith(bin_num):
                filtered_cards.append(card)
    else:
        filtered_cards = all_cards
    
    if len(filtered_cards) < card_count:
        if hasattr(update, 'message'):
            await update.message.reply_text(
                TEXTS['no_bin_cards'].format(
                    required=card_count,
                    available=len(filtered_cards)
                ) if bin_num else TEXTS['not_enough_cards'].format(
                    required=card_count,
                    available=len(filtered_cards)
                ),
                reply_markup=back_to_menu_reply_keyboard(),
                parse_mode='HTML'
            )
        else:
            await update.edit_message_text(
                TEXTS['no_bin_cards'].format(
                    required=card_count,
                    available=len(filtered_cards)
                ) if bin_num else TEXTS['not_enough_cards'].format(
                    required=card_count,
                    available=len(filtered_cards)
                ),
                parse_mode='HTML'
            )
        return False
    
    selected_cards = random.sample(filtered_cards, card_count)
    
    for card_to_remove in selected_cards:
        if card_to_remove in all_cards:
            all_cards.remove(card_to_remove)
            
            for file_info in get_card_files():
                with open(file_info['path'], 'r', encoding='utf-8') as f:
                    cards_in_file = [line.strip() for line in f if line.strip()]
                
                if card_to_remove in cards_in_file:
                    cards_in_file.remove(card_to_remove)
                    with open(file_info['path'], 'w', encoding='utf-8') as f:
                        for card in cards_in_file:
                            f.write(card + '\n')
                    break
    
    with open(CURRENT_CARDS_FILE, 'w', encoding='utf-8') as f:
        for card in all_cards:
            f.write(card + '\n')
    
    user_data['balance'] -= required_amount
    user_data['total_spent'] += required_amount
    user_data['month_spent'] += required_amount
    user_data['month_cards'] += card_count
    
    for i, card in enumerate(selected_cards):
        card_parts = card.split('|')
        card_number = card_parts[0] if len(card_parts) > 0 else ""
        current_bin_num = card_number[:6] if card_number and len(card_number) >= 6 else None
        
        bin_info = None
        if current_bin_num and len(current_bin_num) >= 4:
            try:
                bin_info = get_bin_info(current_bin_num)
            except Exception as e:
                bin_info = get_default_bin_info(current_bin_num)
        
        card_record = {
            'date': datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
            'card': card,
            'price': required_amount / card_count,
            'type': package_info['name'],
            'bin_info': bin_info,
            'bin_number': current_bin_num,
            'package_type': package_type,
            'status': 'pending_feedback'
        }
        user_data['purchased_cards'].append(card_record)
    
    update_user_data(user_id, user_data)
    
    transaction_desc = f"{package_info['name']} package purchase ({card_count} pcs)"
    if bin_num:
        transaction_desc += f" (BIN: {bin_num})"
    
    add_transaction(user_id, 'purchase', -required_amount, transaction_desc)
    
    message = f"✅ <b>{package_info['name'].upper()} PACKAGE PURCHASED!</b>\n\n"
    message += f"📦 <b>Package Info:</b>\n"
    message += f"Quantity: <b>{card_count} cards</b>\n"
    message += f"Price: <code>${required_amount:.2f}</code>\n\n"
    
    if bin_num:
        message += f"🎯 <b>BIN:</b> <code>{bin_num}</code>\n\n"
    
    message += "📄 <b>Your Cards:</b>\n\n"
    
    for i, card in enumerate(selected_cards, 1):
        card_parts = card.split('|')
        if len(card_parts) >= 5:
            formatted_card = f"<code>{card_parts[0]}|{card_parts[1]}|{card_parts[2]}|{card_parts[3]}|{card_parts[4]}</code>"
        else:
            formatted_card = f"<code>{card}</code>"
        
        message += f"{i}. {formatted_card}\n\n"
    
    message += f"💸 <b>Spent:</b> <code>${required_amount:.2f}</code>\n"
    message += f"💰 <b>Remaining:</b> <code>${user_data['balance']:.2f}</code>\n\n"
    message += "⚠️ <b>Note:</b> You can report card status collectively."
    
    if hasattr(update, 'message'):
        await update.message.reply_text(
            message,
            parse_mode='HTML'
        )
    else:
        await update.edit_message_text(
            message,
            parse_mode='HTML'
        )
    
    feedback_message = "👇 <b>Report package status:</b>"
    
    if hasattr(update, 'message'):
        await update.message.reply_text(
            feedback_message,
            reply_markup=card_feedback_keyboard(),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            feedback_message,
            reply_markup=card_feedback_keyboard(),
            parse_mode='HTML'
        )
    
    return True

# --- BOT FUNCTIONS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        await update.message.reply_text(
            TEXTS['spam_warning'],
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    user = update.effective_user
    
    if user.is_bot:
        await update.message.reply_text("❌ Bots cannot use this!")
        return ConversationHandler.END
    
    if is_user_banned(user.id):
        await update.message.reply_text(
            TEXTS['banned'],
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    user_id = user.id
    user_data = get_user_data(user_id)
    
    user_data['username'] = user.username or user.first_name
    update_user_data(user_id, user_data)
    
    if user_data['language'] is None:
        await update.message.reply_text(
            TEXTS['welcome'],
            reply_markup=language_inline_keyboard(),
            parse_mode='HTML'
        )
        return LANGUAGE
    else:
        if not user_data.get('has_seen_welcome', False):
            username = user.username or user.first_name
            await update.message.reply_text(
                TEXTS['welcome_back'].format(username=username),
                reply_markup=main_menu_reply_keyboard(),
                parse_mode='HTML'
            )
            user_data['has_seen_welcome'] = True
            update_user_data(user_id, user_data)
        else:
            await update.message.reply_text(
                TEXTS['main_menu'],
                reply_markup=main_menu_reply_keyboard(),
                parse_mode='HTML'
            )
        
        return MAIN_MENU

async def language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang = query.data.split('_')[1]
    user_id = query.from_user.id
    
    user_data = get_user_data(user_id)
    user_data['language'] = lang
    user_data['has_seen_welcome'] = False
    update_user_data(user_id, user_data)
    
    await query.edit_message_text(
        TEXTS['lang_selected'],
        parse_mode='HTML'
    )
    
    await query.message.reply_text(
        TEXTS['main_menu'],
        reply_markup=main_menu_reply_keyboard(),
        parse_mode='HTML'
    )
    return MAIN_MENU

# --- BIN INPUT HANDLER ---
async def handle_bin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN input"""
    if is_spamming(update.effective_user.id):
        return MAIN_MENU
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    bin_num = update.message.text.strip()
    
    if not (6 <= len(bin_num) <= 8) or not bin_num.isdigit():
        await update.message.reply_text(
            "❌ Invalid BIN! Must be 6-8 digits.",
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    package_info = CARD_PRICES['custom']
    
    message = f"🎯 <b>Custom Card Package</b>\n\n"
    message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
    message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
    message += f"• BIN: <code>{bin_num}</code>\n\n"
    message += "Do you confirm?"
    
    context.user_data['selected_bin'] = bin_num
    
    await update.message.reply_text(
        message,
        reply_markup=purchase_confirm_keyboard('custom'),
        parse_mode='HTML'
    )

# --- PROMO CODE HANDLER ---
async def handle_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle promo code input"""
    if is_spamming(update.effective_user.id):
        return MAIN_MENU
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    promo_code = update.message.text.strip().upper()
    
    promo_codes = load_promo_codes()
    
    if promo_code in promo_codes and not promo_codes[promo_code]['used']:
        amount = promo_codes[promo_code]['amount']
        
        user_data['balance'] += amount
        update_user_data(user_id, user_data)
        
        promo_codes[promo_code]['used'] = True
        promo_codes[promo_code]['used_by'] = user_id
        promo_codes[promo_code]['used_date'] = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
        save_promo_codes(promo_codes)
        
        add_balance_history(user_id, amount, f'Code: {promo_code}')
        
        await update.message.reply_text(
            TEXTS['promo_success'].format(amount=amount),
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            TEXTS['promo_invalid'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
    
    return MAIN_MENU

# --- CARD FEEDBACK HANDLER ---
async def handle_card_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    action = query.data
    
    if action == 'card_live':
        await query.edit_message_text(
            "✅ <b>Thank you! You reported your card package is working.</b>",
            parse_mode='HTML'
        )
    elif action == 'card_declined':
        if user_data['purchased_cards']:
            recent_cards = []
            for card in reversed(user_data['purchased_cards']):
                if card.get('status') == 'pending_feedback':
                    recent_cards.append(card)
                    if len(recent_cards) >= 5:
                        break
            
            if recent_cards:
                total_amount = sum(card['price'] for card in recent_cards)
                
                refund_id = f"refund_{user_id}_{int(time.time())}"
                PENDING_REFUNDS[refund_id] = {
                    'user_id': user_id,
                    'user_name': user_data['username'] or f"ID: {user_id}",
                    'cards': [card['card'] for card in recent_cards],
                    'amount': total_amount,
                    'date': recent_cards[0]['date'],
                    'status': 'pending'
                }
                
                admin_message = TEXTS['card_report_received'].format(
                    user=f"{user_data['username']} (ID: {user_id})",
                    card=f"<code>{len(recent_cards)} card package</code>"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_message,
                        reply_markup=admin_refund_keyboard(refund_id),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Could not send admin message: {e}")
                
                await query.edit_message_text(
                    TEXTS['card_declined'],
                    parse_mode='HTML'
                )
    
    await query.message.reply_text(
        TEXTS['main_menu'],
        reply_markup=main_menu_reply_keyboard(),
        parse_mode='HTML'
    )
    return MAIN_MENU

# --- REFUND APPROVE/REJECT HANDLER ---
async def handle_refund_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('refund_approve_'):
        refund_id = data.replace('refund_approve_', '')
        if refund_id in PENDING_REFUNDS:
            refund_info = PENDING_REFUNDS[refund_id]
            user_id = refund_info['user_id']
            amount = refund_info['amount']
            
            user_data = get_user_data(user_id)
            user_data['balance'] += amount
            user_data['total_spent'] -= amount
            user_data['month_spent'] -= amount
            
            for card_num in refund_info['cards']:
                for i, card in enumerate(user_data['purchased_cards']):
                    if card['card'] == card_num:
                        user_data['purchased_cards'][i]['status'] = 'refunded'
                        break
            
            update_user_data(user_id, user_data)
            
            add_balance_history(user_id, amount, f'Card package refund')
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=TEXTS['refund_approved'].format(amount=amount),
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Could not send message to user: {e}")
            
            await query.edit_message_text(
                f"✅ <b>Refund approved!</b>\n\n"
                f"User: {refund_info['user_name']}\n"
                f"Refund: <code>${amount:.2f}</code>\n"
                f"Cards: <code>{len(refund_info['cards'])} pcs</code>",
                parse_mode='HTML'
            )
            
            del PENDING_REFUNDS[refund_id]
        else:
            await query.answer("❌ Refund not found!", show_alert=True)
    
    elif data.startswith('refund_reject_'):
        refund_id = data.replace('refund_reject_', '')
        if refund_id in PENDING_REFUNDS:
            refund_info = PENDING_REFUNDS[refund_id]
            user_id = refund_info['user_id']
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=TEXTS['refund_rejected'],
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Could not send message to user: {e}")
            
            await query.edit_message_text(
                f"❌ <b>Refund rejected!</b>\n\n"
                f"User: {refund_info['user_name']}\n"
                f"Cards: <code>{len(refund_info['cards'])} pcs</code>",
                parse_mode='HTML'
            )
            
            del PENDING_REFUNDS[refund_id]
        else:
            await query.answer("❌ Refund not found!", show_alert=True)

# --- PACKAGE PURCHASE HANDLER ---
async def handle_package_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle card package purchase"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    data = query.data
    
    if data.startswith('buy_'):
        package_type = data.replace('buy_', '')
        
        if package_type not in CARD_PRICES:
            await query.answer("❌ Invalid package!", show_alert=True)
            return
        
        bin_num = context.user_data.get('selected_bin') if package_type == 'custom' else None
        
        success = await send_card_package_to_user(query, user_id, user_data, package_type, bin_num)
        
        if success:
            if 'selected_bin' in context.user_data:
                del context.user_data['selected_bin']
            
            await query.message.reply_text(
                TEXTS['main_menu'],
                reply_markup=main_menu_reply_keyboard(),
                parse_mode='HTML'
            )
        return MAIN_MENU
    
    elif data.startswith('cancel_'):
        package_type = data.replace('cancel_', '')
        
        await query.edit_message_text(
            f"❌ <b>{CARD_PRICES[package_type]['name']} package purchase cancelled.</b>",
            parse_mode='HTML'
        )
        
        if 'selected_bin' in context.user_data:
            del context.user_data['selected_bin']
        
        await query.message.reply_text(
            TEXTS['main_menu'],
            reply_markup=main_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU

# --- DEPOSIT HANDLERS ---
async def handle_deposit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    action = query.data
    
    if action == 'cancel_deposit':
        await query.edit_message_text(
            "❌ <b>Deposit cancelled.</b>",
            parse_mode='HTML'
        )
        await query.message.reply_text(
            TEXTS['main_menu'],
            reply_markup=main_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    deposit_amounts = {
        'deposit_5': 5.0,
        'deposit_10': 10.0,
        'deposit_20': 20.0,
        'deposit_50': 50.0,
        'deposit_100': 100.0
    }
    
    if action not in deposit_amounts:
        await query.answer("❌ Invalid selection!", show_alert=True)
        return
    
    amount = deposit_amounts[action]
    
    deposit_id = f"deposit_{user_id}_{int(time.time())}"
    PENDING_DEPOSITS[deposit_id] = {
        'user_id': user_id,
        'user_name': user_data['username'] or f"ID: {user_id}",
        'amount': amount,
        'date': datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
        'status': 'pending'
    }
    
    deposit_text_key = f'deposit_{int(amount)}'
    if deposit_text_key in TEXTS:
        message = TEXTS[deposit_text_key]
    else:
        message = f"💰 <b>{amount} USD PURCHASE</b>\n\n"
        message += f"Please complete payment and click <b>Sent</b> button."
    
    await query.edit_message_text(
        message,
        reply_markup=deposit_confirm_keyboard(deposit_id),
        parse_mode='HTML'
    )

async def handle_deposit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit confirmation"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('deposit_sent_'):
        deposit_id = data.replace('deposit_sent_', '')
        
        if deposit_id in PENDING_DEPOSITS:
            deposit_info = PENDING_DEPOSITS[deposit_id]
            user_id = deposit_info['user_id']
            
            admin_message = TEXTS['deposit_request_received'].format(
                user=f"{deposit_info['user_name']} (ID: {user_id})",
                amount=deposit_info['amount'],
                deposit_id=deposit_id
            )
            
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=admin_message,
                    reply_markup=admin_deposit_keyboard(deposit_id),
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Could not send admin message: {e}")
            
            await query.edit_message_text(
                TEXTS['deposit_confirm'],
                parse_mode='HTML'
            )
            
            await query.message.reply_text(
                TEXTS['main_menu'],
                reply_markup=main_menu_reply_keyboard(),
                parse_mode='HTML'
            )
            return MAIN_MENU
    
    elif data.startswith('deposit_cancel_'):
        deposit_id = data.replace('deposit_cancel_', '')
        
        if deposit_id in PENDING_DEPOSITS:
            del PENDING_DEPOSITS[deposit_id]
        
        await query.edit_message_text(
            "❌ <b>Deposit cancelled.</b>",
            parse_mode='HTML'
        )
        
        await query.message.reply_text(
            TEXTS['main_menu'],
            reply_markup=main_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU

async def handle_deposit_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin deposit decision"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('deposit_approve_'):
        deposit_id = data.replace('deposit_approve_', '')
        
        if deposit_id in PENDING_DEPOSITS:
            deposit_info = PENDING_DEPOSITS[deposit_id]
            user_id = deposit_info['user_id']
            amount = deposit_info['amount']
            
            user_data = get_user_data(user_id)
            user_data['balance'] += amount
            update_user_data(user_id, user_data)
            
            add_balance_history(user_id, amount, f'Deposit')
            add_transaction(user_id, 'deposit', amount, f'Deposit (${amount})')
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=TEXTS['deposit_approved'].format(
                        amount=amount,
                        new_balance=user_data['balance']
                    ),
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Could not send message to user: {e}")
            
            await query.edit_message_text(
                f"✅ <b>Deposit request approved!</b>\n\n"
                f"User: {deposit_info['user_name']}\n"
                f"Amount: <code>${amount:.2f}</code>\n"
                f"Request ID: <code>{deposit_id}</code>",
                parse_mode='HTML'
            )
            
            del PENDING_DEPOSITS[deposit_id]
    
    elif data.startswith('deposit_reject_'):
        deposit_id = data.replace('deposit_reject_', '')
        
        if deposit_id in PENDING_DEPOSITS:
            deposit_info = PENDING_DEPOSITS[deposit_id]
            user_id = deposit_info['user_id']
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=TEXTS['deposit_rejected'],
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Could not send message to user: {e}")
            
            await query.edit_message_text(
                f"❌ <b>Deposit request rejected!</b>\n\n"
                f"User: {deposit_info['user_name']}\n"
                f"Amount: <code>${deposit_info['amount']:.2f}</code>\n"
                f"Request ID: <code>{deposit_id}</code>",
                parse_mode='HTML'
            )
            
            del PENDING_DEPOSITS[deposit_id]

# --- CALLBACK QUERY HANDLER ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('lang_'):
        await language_selection(update, context)
    
    elif data.startswith('buy_') or data.startswith('cancel_'):
        await handle_package_purchase(update, context)
    
    elif data in ['card_live', 'card_declined']:
        await handle_card_feedback(update, context)
    
    elif data.startswith('refund_'):
        await handle_refund_decision(update, context)
    
    elif data.startswith('deposit_') and (data.endswith('5') or data.endswith('10') or 
                                          data.endswith('20') or data.endswith('50') or 
                                          data.endswith('100') or data == 'cancel_deposit'):
        await handle_deposit_selection(update, context)
    
    elif data.startswith('deposit_sent_') or data.startswith('deposit_cancel_'):
        await handle_deposit_confirm(update, context)
    
    elif data.startswith('deposit_approve_') or data.startswith('deposit_reject_'):
        await handle_deposit_decision(update, context)
    
    elif data == 'view_credit_bins':
        cards = load_cards()
        credit_bins = {}
        for card in cards:
            if 'debit' not in card.lower():
                bin_num = card[:6]
                if bin_num.isdigit():
                    credit_bins[bin_num] = credit_bins.get(bin_num, 0) + 1
        
        lines = ["```", "BIN      STOCK  BANK", "───────────────────────────────────"]
        for i, (bin_num, count) in enumerate(list(credit_bins.items())[:15]):
            lines.append(f"{bin_num:<8} {count:<5}")
        
        if len(credit_bins) > 15:
            lines.append(f"\n📊 Total {len(credit_bins)} different BINs")
        
        lines.append("```")
        lines.append("💡 Use /custom <number> to buy")
        
        message = "\n".join(lines)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Next", callback_data='credit_bins_next_15')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_bin_query')]
        ])
        
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    elif data == 'view_debit_bins':
        cards = load_cards()
        debit_bins = {}
        for card in cards:
            if 'debit' in card.lower():
                bin_num = card[:6]
                if bin_num.isdigit():
                    debit_bins[bin_num] = debit_bins.get(bin_num, 0) + 1
        
        lines = ["```", "BIN      STOCK  BANK", "───────────────────────────────────"]
        for i, (bin_num, count) in enumerate(list(debit_bins.items())[:15]):
            lines.append(f"{bin_num:<8} {count:<5}")
        
        if len(debit_bins) > 15:
            lines.append(f"\n📊 Total {len(debit_bins)} different BINs")
        
        lines.append("```")
        lines.append("💡 Use /economic to buy")
        
        message = "\n".join(lines)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Next", callback_data='debit_bins_next_15')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_bin_query')]
        ])
        
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    elif data == 'back_to_bin_query':
        await query.edit_message_text(
            TEXTS['available_bins'],
            reply_markup=bin_type_inline_keyboard(),
            parse_mode='HTML'
        )
    
    elif data.startswith('credit_bins_next_') or data.startswith('debit_bins_next_'):
        await query.answer("⏭️ Feature not ready yet!")

# --- COMMAND HANDLERS ---
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    await update.message.reply_text(
        TEXTS['buy_menu'],
        reply_markup=buy_menu_reply_keyboard(),
        parse_mode='HTML'
    )
    return BUY_CARD

async def fast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy fast card package"""
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    package_info = CARD_PRICES['fast']
    
    message = f"⚡ <b>Fast Card Package</b>\n\n"
    message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
    message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
    message += f"• Feature: Mixed banks\n\n"
    message += "Do you confirm?"
    
    await update.message.reply_text(
        message,
        reply_markup=purchase_confirm_keyboard('fast'),
        parse_mode='HTML'
    )

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy custom card package"""
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /custom <BIN>\nExample: /custom 454360",
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return
    
    bin_num = context.args[0].strip()
    
    if not (6 <= len(bin_num) <= 8) or not bin_num.isdigit():
        await update.message.reply_text(
            "❌ Invalid BIN! Must be 6-8 digits.",
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return
    
    context.user_data['selected_bin'] = bin_num
    
    package_info = CARD_PRICES['custom']
    
    message = f"🎯 <b>Custom Card Package</b>\n\n"
    message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
    message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
    message += f"• BIN: <code>{bin_num}</code>\n\n"
    message += "Do you confirm?"
    
    await update.message.reply_text(
        message,
        reply_markup=purchase_confirm_keyboard('custom'),
        parse_mode='HTML'
    )

async def economic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy economic card package"""
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    package_info = CARD_PRICES['economic']
    
    message = f"💎 <b>Economic Card Package</b>\n\n"
    message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
    message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
    message += f"• Feature: Mixed banks\n\n"
    message += "Do you confirm?"
    
    await update.message.reply_text(
        message,
        reply_markup=purchase_confirm_keyboard('economic'),
        parse_mode='HTML'
    )

async def mycards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['purchased_cards']:
        await update.message.reply_text(
            TEXTS['no_cards'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return
    
    packages = {}
    for card_info in user_data['purchased_cards']:
        package_type = card_info.get('package_type', 'unknown')
        if package_type not in packages:
            packages[package_type] = {
                'count': 0,
                'total_price': 0,
                'last_date': card_info['date'],
                'cards': []
            }
        packages[package_type]['count'] += 1
        packages[package_type]['total_price'] += card_info['price']
        packages[package_type]['cards'].append(card_info)
    
    cards_text = TEXTS['my_cards']
    cards_text += f"📦 <b>Total Packages: {len(packages)}</b>\n\n"
    
    for package_type, package_data in packages.items():
        package_name = CARD_PRICES.get(package_type, {}).get('name', package_type)
        cards_text += f"📦 <b>{package_name} Package</b>\n"
        cards_text += f"• Quantity: <code>{package_data['count']} cards</code>\n"
        cards_text += f"• Total: <code>${package_data['total_price']:.2f}</code>\n"
        cards_text += f"• Last Date: {package_data['last_date']}\n\n"
    
    await update.message.reply_text(
        cards_text,
        reply_markup=back_to_menu_reply_keyboard(),
        parse_mode='HTML'
    )

async def handle_reply_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    text = update.message.text
    
    if text == "💰 Prices":
        await update.message.reply_text(
            TEXTS['price_list'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "👤 Account":
        profile_text = TEXTS['profile'].format(
            user_id=user_id,
            username=update.message.from_user.username or update.message.from_user.first_name,
            join_date=user_data['join_date'],
            balance=user_data['balance'],
            month_spent=user_data['month_spent'],
            month_cards=user_data['month_cards'],
            total_spent=user_data['total_spent']
        )
        await update.message.reply_text(
            profile_text,
            reply_markup=profile_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "📚 Help":
        await update.message.reply_text(
            TEXTS['help'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "☎️ Support":
        await update.message.reply_text(
            TEXTS['contact'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "🛍️ Buy":
        await update.message.reply_text(
            TEXTS['buy_menu'],
            reply_markup=buy_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return BUY_CARD
    
    elif text == "💳 Balance":
        await update.message.reply_text(
            TEXTS['deposit_amount'],
            reply_markup=deposit_amount_keyboard(),
            parse_mode='HTML'
        )
        return DEPOSIT_AMOUNT
    
    elif text == "🎟️ Code":
        await update.message.reply_text(
            TEXTS['promo_input'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return PROMO_INPUT
    
    elif text == "🔍 Stock Check":
        await update.message.reply_text(
            TEXTS['available_bins'],
            reply_markup=bin_type_inline_keyboard(),
            parse_mode='HTML'
        )
        return BIN_QUERY
    
    elif text == "📜 My Cards":
        if not user_data['purchased_cards']:
            await update.message.reply_text(
                TEXTS['no_cards'],
                reply_markup=profile_reply_keyboard(),
                parse_mode='HTML'
            )
            return MAIN_MENU
        
        packages = {}
        for card_info in user_data['purchased_cards']:
            package_type = card_info.get('package_type', 'unknown')
            if package_type not in packages:
                packages[package_type] = {
                    'count': 0,
                    'total_price': 0,
                    'last_date': card_info['date'],
                    'cards': []
                }
            packages[package_type]['count'] += 1
            packages[package_type]['total_price'] += card_info['price']
            packages[package_type]['cards'].append(card_info)
        
        cards_text = TEXTS['my_cards']
        cards_text += f"📦 <b>Total Packages: {len(packages)}</b>\n\n"
        
        for package_type, package_data in packages.items():
            package_name = CARD_PRICES.get(package_type, {}).get('name', package_type)
            cards_text += f"📦 <b>{package_name} Package</b>\n"
            cards_text += f"• Quantity: <code>{package_data['count']} cards</code>\n"
            cards_text += f"• Total: <code>${package_data['total_price']:.2f}</code>\n"
            cards_text += f"• Last Date: {package_data['last_date']}\n\n"
        
        await update.message.reply_text(
            cards_text,
            reply_markup=profile_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "📊 Transactions":
        if not user_data['transactions']:
            await update.message.reply_text(
                TEXTS['no_transactions'],
                reply_markup=profile_reply_keyboard(),
                parse_mode='HTML'
            )
            return MAIN_MENU
        
        trans_text = TEXTS['transactions']
        for i, trans in enumerate(user_data['transactions'][-10:], 1):
            amount_sign = "+" if trans['amount'] >= 0 else ""
            trans_text += f"{i}. {trans['date']}\n"
            trans_text += f"   {trans['type']}: <code>{amount_sign}${trans['amount']:.2f}</code>\n"
            trans_text += f"   {trans['description']}\n\n"
        
        await update.message.reply_text(
            trans_text,
            reply_markup=profile_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "💰 History":
        if not user_data['balance_history']:
            await update.message.reply_text(
                TEXTS['no_balance_history'],
                reply_markup=profile_reply_keyboard(),
                parse_mode='HTML'
            )
            return MAIN_MENU
        
        history_text = TEXTS['balance_history']
        for i, history in enumerate(user_data['balance_history'][-10:], 1):
            change_sign = "+" if history['change'] >= 0 else ""
            history_text += f"{i}. {history['date']}\n"
            history_text += f"   Change: <code>{change_sign}${history['change']:.2f}</code>\n"
            history_text += f"   Reason: {history['reason']}\n"
            history_text += f"   Final Balance: <code>${history['balance_after']:.2f}</code>\n\n"
        
        await update.message.reply_text(
            history_text,
            reply_markup=profile_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "💳 Add Balance":
        await update.message.reply_text(
            TEXTS['deposit_amount'],
            reply_markup=deposit_amount_keyboard(),
            parse_mode='HTML'
        )
        return DEPOSIT_AMOUNT
    
    elif text == "🌍 Language":
        await update.message.reply_text(
            TEXTS['welcome'],
            reply_markup=language_inline_keyboard(),
            parse_mode='HTML'
        )
        return LANGUAGE
    
    elif text == "🔙 Main Menu":
        await update.message.reply_text(
            TEXTS['main_menu'],
            reply_markup=main_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return MAIN_MENU
    
    elif text == "🎯 Buy Custom":
        await update.message.reply_text(
            TEXTS['bin_purchase'],
            reply_markup=back_to_menu_reply_keyboard(),
            parse_mode='HTML'
        )
        return BIN_INPUT
    
    elif text == "⚡ Buy Fast":
        user_id = update.message.from_user.id
        user_data = get_user_data(user_id)
        
        package_info = CARD_PRICES['fast']
        
        message = f"⚡ <b>Fast Card Package</b>\n\n"
        message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
        message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
        message += f"• Feature: Mixed banks\n\n"
        message += "Do you confirm?"
        
        await update.message.reply_text(
            message,
            reply_markup=purchase_confirm_keyboard('fast'),
            parse_mode='HTML'
        )
    
    elif text == "💎 Buy Economic":
        user_id = update.message.from_user.id
        user_data = get_user_data(user_id)
        
        package_info = CARD_PRICES['economic']
        
        message = f"💎 <b>Economic Card Package</b>\n\n"
        message += f"• Price: <code>${package_info['price']:.2f}</code>\n"
        message += f"• Quantity: <b>{package_info['count']} cards</b>\n"
        message += f"• Feature: Mixed banks\n\n"
        message += "Do you confirm?"
        
        await update.message.reply_text(
            message,
            reply_markup=purchase_confirm_keyboard('economic'),
            parse_mode='HTML'
        )

# --- ADMIN COMMANDS ---
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    admin_text = "🔐 <b>ADMIN COMMANDS</b>\n\n"
    admin_text += "📤 <b>File Operations:</b>\n"
    admin_text += "• /filelist - List card files\n"
    admin_text += "• /filedelete <number> - Delete file\n"
    admin_text += "• /upload - Upload normal cards\n"
    admin_text += "• /add - Add cards via message\n\n"
    admin_text += "💰 <b>Promo Codes:</b>\n"
    admin_text += "• /createcode <amount> - Create code\n\n"
    admin_text += "📊 <b>Statistics:</b>\n"
    admin_text += "• /stats - Total statistics\n\n"
    admin_text += "👥 <b>User Management:</b>\n"
    admin_text += "• /giveaway <amount> - Give money to all\n"
    admin_text += "• /announce <message> - Send announcement\n"
    admin_text += "• /ban <id> - Ban user\n"
    admin_text += "• /unban <id> - Unban user\n\n"
    admin_text += "❓ <b>Other:</b>\n"
    admin_text += "• /admin - Show this message"
    
    await update.message.reply_text(admin_text, parse_mode='HTML')

async def admin_filelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    files = get_card_files()
    all_cards = load_cards()
    
    if not files:
        await update.message.reply_text("📭 No card files!")
        return
    
    message = "📁 <b>CARD FILES</b>\n\n"
    message += f"📊 Total cards: <code>{len(all_cards)}</code> pcs\n\n"
    
    for i, file_info in enumerate(files, 1):
        message += f"{i}. <b>{file_info['name']}</b>\n"
        message += f"   📄 Cards: <code>{file_info['cards']}</code> pcs\n"
        message += f"   📍 Path: <code>{file_info['path']}</code>\n\n"
    
    message += f"💰 <b>PACKAGE PRICES:</b>\n"
    message += f"• Economic: $1 → 20 cards\n"
    message += f"• Fast: $3 → 50 cards\n"
    message += f"• Custom: $5 → 70 cards\n"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def admin_filedelete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /filedelete <number>")
        return
    
    try:
        file_num = int(context.args[0])
        files = get_card_files()
        
        if 1 <= file_num <= len(files):
            file_to_delete = files[file_num - 1]
            os.remove(file_to_delete['path'])
            
            merge_all_cards()
            
            await update.message.reply_text(
                f"✅ <b>File deleted!</b>\n\n"
                f"📄 File: {file_to_delete['name']}\n"
                f"🗑️ Deleted cards: {file_to_delete['cards']} pcs\n\n"
                f"📊 New total: {len(load_cards())} cards",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ Invalid number! Must be 1-{len(files)}.")
    except ValueError:
        await update.message.reply_text("❌ Invalid number!")

async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    await update.message.reply_text(
        "📤 Please send NORMAL card data file:\n"
        "Format: CardNo|EXP|CVV|Name Surname|Bank\n\n"
        "<i>File will be added automatically after sending.</i>",
        parse_mode='HTML'
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    document = update.message.document
    file = await document.get_file()
    
    temp_file = f"temp_{int(time.time())}.txt"
    await file.download_to_drive(temp_file)
    
    try:
        with open(temp_file, 'r', encoding='utf-8') as f:
            cards = [line.strip() for line in f if line.strip()]
        
        print(f"📥 {len(cards)} cards read")
        
        filename, card_count = add_cards_to_file(cards)
        all_cards = load_cards()
        total_count = len(all_cards)
        
        await update.message.reply_text(
            f"✅ <b>File uploaded successfully!</b>\n\n"
            f"📄 File: <code>{filename}</code>\n"
            f"📊 Added: <code>{card_count}</code> cards\n"
            f"📈 New total: <code>{total_count}</code> cards\n\n"
            f"💰 <b>Package Calculation:</b>\n"
            f"• Economic Package: <code>{total_count // 20} pcs</code>\n"
            f"• Fast Package: <code>{total_count // 50} pcs</code>\n"
            f"• Custom Package: <code>{total_count // 70} pcs</code>",
            parse_mode='HTML'
        )
        print(f"✅ {card_count} normal cards added. Total: {total_count}")
    
    except Exception as e:
        print(f"❌ File processing error: {e}")
        await update.message.reply_text(
            f"❌ <b>Error processing file!</b>\n\n"
            f"Error: {str(e)}",
            parse_mode='HTML'
        )
    
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

# --- /ADD COMMAND FUNCTIONS ---
async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 <b>Add cards mode</b>\n\n"
        "Please send cards one per line:\n"
        "Format: CardNo|EXP|CVV|Name Surname|Bank\n\n"
        "Max 100 lines can be sent.\n"
        "Type /cancel to finish.",
        parse_mode='HTML'
    )
    
    return ADMIN_ADD_CARDS

async def handle_add_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    text = update.message.text
    
    if text == '/cancel':
        await update.message.reply_text("❌ Card addition cancelled.")
        return ConversationHandler.END
    
    lines = text.strip().split('\n')
    valid_cards = []
    
    for line in lines:
        line = line.strip()
        if line and '|' in line:
            valid_cards.append(line)
    
    if not valid_cards:
        await update.message.reply_text("❌ No valid cards found!")
        return ADMIN_ADD_CARDS
    
    if len(valid_cards) > 100:
        valid_cards = valid_cards[:100]
        await update.message.reply_text(f"⚠️ Max 100 lines accepted. First 100 taken.")
    
    filename, card_count = add_cards_to_file(valid_cards)
    all_cards = load_cards()
    total_count = len(all_cards)
    
    await update.message.reply_text(
        f"✅ <b>Cards added!</b>\n\n"
        f"📄 File: <code>{filename}</code>\n"
        f"📊 Added: <code>{card_count}</code> cards\n"
        f"📈 New total: <code>{total_count}</code> cards\n\n"
        f"💰 <b>Package Calculation:</b>\n"
        f"• Economic Package: <code>{total_count // 20} pcs</code>\n"
        f"• Fast Package: <code>{total_count // 50} pcs</code>\n"
        f"• Custom Package: <code>{total_count // 70} pcs</code>",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END

async def cancel_add_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    await update.message.reply_text("❌ Card addition cancelled.")
    return ConversationHandler.END

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    users = load_users()
    all_cards = load_cards()
    
    total_users = len(users)
    total_balance = sum(user['balance'] for user in users.values())
    total_spent = sum(user['total_spent'] for user in users.values())
    total_cards_sold = sum(user['month_cards'] for user in users.values())
    
    current_month = date.today().strftime('%m/%Y')
    month_spent = sum(user['month_spent'] for user in users.values())
    month_cards = sum(user['month_cards'] for user in users.values())
    
    package_sales = {'economic': 0, 'fast': 0, 'custom': 0}
    for user in users.values():
        for card in user['purchased_cards']:
            package_type = card.get('package_type')
            if package_type in package_sales:
                package_sales[package_type] += 1
    
    message = "📊 <b>GLOBAL STATISTICS</b>\n\n"
    message += f"👥 Total users: <code>{total_users}</code>\n"
    message += f"💰 Total balance: <code>${total_balance:.2f}</code>\n"
    message += f"💸 Total spend: <code>${total_spent:.2f}</code>\n"
    message += f"💳 Total cards sold: <code>{total_cards_sold}</code>\n\n"
    
    message += f"📅 <b>{current_month} Month</b>\n"
    message += f"• Spend: <code>${month_spent:.2f}</code>\n"
    message += f"• Cards sold: <code>{month_cards}</code>\n\n"
    
    message += f"📦 <b>Stock Status</b>\n"
    message += f"• Available cards: <code>{len(all_cards)}</code>\n"
    message += f"• File count: <code>{len(get_card_files())}</code>\n\n"
    
    message += f"🛍️ <b>Package Sales</b>\n"
    message += f"• Economic: <code>{package_sales['economic'] // 20} packages</code>\n"
    message += f"• Fast: <code>{package_sales['fast'] // 50} packages</code>\n"
    message += f"• Custom: <code>{package_sales['custom'] // 70} packages</code>\n\n"
    
    top_users = sorted(users.items(), key=lambda x: x[1]['total_spent'], reverse=True)[:5]
    
    message += "🏆 <b>Top Spenders</b>\n"
    for i, (user_id, user_data) in enumerate(top_users, 1):
        username = user_data.get('username', f'ID: {user_id}')
        message += f"{i}. {username}: <code>${user_data['total_spent']:.2f}</code>\n"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def admin_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        amount = float(context.args[0])
        
        users = load_users()
        count = 0
        
        for user_id, user_data in users.items():
            user_data['balance'] += amount
            users[user_id] = user_data
            add_balance_history(int(user_id), amount, f'Admin bonus')
            count += 1
        
        save_users(users)
        
        await update.message.reply_text(
            f"✅ <b>Bonus distributed!</b>\n\n"
            f"💰 Amount: <code>${amount:.2f}</code>\n"
            f"👥 Users: <code>{count}</code> people\n"
            f"📈 Total: <code>${amount * count:.2f}</code>",
            parse_mode='HTML'
        )
    except:
        await update.message.reply_text("❌ Usage: /giveaway <amount>")

async def admin_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /announce <message>")
        return
    
    message = ' '.join(context.args)
    users = load_users()
    count = 0
    failed = 0
    
    await update.message.reply_text(f"📢 Sending announcement... to {len(users)} users")
    
    for user_id in users.keys():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"📢 <b>ANNOUNCEMENT</b>\n\n{message}",
                parse_mode='HTML'
            )
            count += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ <b>Announcement complete!</b>\n\n"
        f"📤 Sent: <code>{count}</code>\n"
        f"❌ Failed: <code>{failed}</code>",
        parse_mode='HTML'
    )

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(context.args[0])
        ban_user(user_id)
        
        await update.message.reply_text(
            f"✅ <b>User banned!</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>",
            parse_mode='HTML'
        )
    except:
        await update.message.reply_text("❌ Usage: /ban <id>")

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(context.args[0])
        unban_user(user_id)
        
        await update.message.reply_text(
            f"✅ <b>User unbanned!</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>",
            parse_mode='HTML'
        )
    except:
        await update.message.reply_text("❌ Usage: /unban <id>")

async def admin_createcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        amount = float(context.args[0]) if context.args else 5.0
        
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        promo_codes = load_promo_codes()
        promo_codes[code] = {
            'amount': amount,
            'created': datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
            'created_by': update.effective_user.id,
            'used': False,
            'used_by': None,
            'used_date': None,
            'expires': (datetime.now() + timedelta(days=30)).strftime('%m/%d/%Y')
        }
        save_promo_codes(promo_codes)
        
        await update.message.reply_text(
            f"✅ Promo code created!\n\n"
            f"🔑 <b>Code:</b> <code>{code}</code>\n"
            f"💰 <b>Value:</b> <code>${amount:.2f}</code>\n"
            f"📅 <b>Created:</b> {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}\n"
            f"⏳ <b>Expires:</b> {(datetime.now() + timedelta(days=30)).strftime('%m/%d/%Y')}",
            parse_mode='HTML'
        )
    except:
        await update.message.reply_text(
            "❌ Usage: /createcode <amount>\nExample: /createcode 5"
        )

# --- USER COMMAND HANDLERS ---
async def show_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    await update.message.reply_text(
        TEXTS['help'],
        reply_markup=back_to_menu_reply_keyboard(),
        parse_mode='HTML'
    )

async def price_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    await update.message.reply_text(
        TEXTS['price_list'],
        reply_markup=back_to_menu_reply_keyboard(),
        parse_mode='HTML'
    )

async def show_contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    await update.message.reply_text(
        TEXTS['contact'],
        reply_markup=back_to_menu_reply_keyboard(),
        parse_mode='HTML'
    )

async def show_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_spamming(update.effective_user.id):
        return
    
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    profile_text = TEXTS['profile'].format(
        user_id=user_id,
        username=update.message.from_user.username or update.message.from_user.first_name,
        join_date=user_data['join_date'],
        balance=user_data['balance'],
        month_spent=user_data['month_spent'],
        month_cards=user_data['month_cards'],
        total_spent=user_data['total_spent']
    )
    
    await update.message.reply_text(
        profile_text,
        reply_markup=back_to_menu_reply_keyboard(),
        parse_mode='HTML'
    )

# --- MAIN FUNCTION ---
def main():
    init_files()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_selection, pattern='^lang_')],
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons)
            ],
            BUY_CARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons)
            ],
            BIN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin_input)],
            PROMO_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_promo_input)],
            BIN_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons),
                CallbackQueryHandler(handle_callback_query)
            ],
            ADMIN_ADD_CARDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_cards),
                CommandHandler('cancel', cancel_add_cards)
            ],
            DEPOSIT_AMOUNT: [
                CallbackQueryHandler(handle_callback_query)
            ]
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # USER COMMANDS
    application.add_handler(CommandHandler('help', show_help_command))
    application.add_handler(CommandHandler('price', price_info_command))
    application.add_handler(CommandHandler('contact', show_contact_command))
    application.add_handler(CommandHandler('profile', show_profile_command))
    
    # NEW COMMANDS
    application.add_handler(CommandHandler('buy', buy_command))
    application.add_handler(CommandHandler('fast', fast_command))
    application.add_handler(CommandHandler('custom', custom_command))
    application.add_handler(CommandHandler('economic', economic_command))
    application.add_handler(CommandHandler('mycards', mycards_command))
    
    # ADMIN COMMANDS
    application.add_handler(CommandHandler('admin', admin_help))
    application.add_handler(CommandHandler('filelist', admin_filelist))
    application.add_handler(CommandHandler('filedelete', admin_filedelete))
    application.add_handler(CommandHandler('upload', admin_upload))
    application.add_handler(CommandHandler('add', admin_add))
    application.add_handler(CommandHandler('stats', admin_stats))
    application.add_handler(CommandHandler('giveaway', admin_giveaway))
    application.add_handler(CommandHandler('announce', admin_announce))
    application.add_handler(CommandHandler('ban', admin_ban))
    application.add_handler(CommandHandler('unban', admin_unban))
    application.add_handler(CommandHandler('createcode', admin_createcode))
    
    # Document handler
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
    
    # Start bot
    print("🤖 Bot starting...")
    print(f"🔐 Admin ID: {ADMIN_ID}")
    print(f"📁 Card directory: {CARDS_DIR}")
    
    all_cards = load_cards()
    print(f"📊 Available cards: {len(all_cards)} pcs")
    
    economic_pkg = len(all_cards) // 20
    fast_pkg = len(all_cards) // 50
    custom_pkg = len(all_cards) // 70
    
    print(f"💰 Package Calculations:")
    print(f"   • Economic ($1): {economic_pkg} packages")
    print(f"   • Fast ($3): {fast_pkg} packages")
    print(f"   • Custom ($5): {custom_pkg} packages")
    
    print("🛡️ Spam protection: Active")
    print("💸 Refund system: ACTIVE")
    print("💰 Deposit system: ACTIVE")
    print("📦 Card packages: ACTIVE")
    print("📝 /add command: ACTIVE")
    print("📡 BIN API: ACTIVE")
    print("✅ Bot ready! Use /start to begin")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        import requests
        print("✅ Requests library available")
    except ImportError:
        print("❌ Requests library not installed!")
        print("📦 Install with: pip install requests")
        exit(1)
    
    main()
