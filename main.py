import logging
import requests
import time
import threading
from flask import Flask, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = 'https://api.51gameapi.com/api/webapi/GetEmerdList'  # Your API URL

# Store user states globally
user_states = {}

# Initialize Flask app
flask_app = Flask(__name__)


@flask_app.route('/')
def index():
    return send_from_directory('', 'alive.html')  # Serve alive.html file


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = (
        "<b>🎉 Welcome to the Prediction Bot! 🎉</b>\n\n"
        "<b>Simply send a number (0-9) to start receiving predictions. "
        "I'll automatically detect your last drawn number and give you predictions based on that. "
        "To begin, use the command: /predict &lt;number&gt;</b>.")
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.HTML)


async def fetch_data() -> dict:
    request_data = {
        "typeId": 1,
        "language": 0,
        "random": "c5acbc8a25b24da1a9ddd084e17cb8b6",
        "signature": "667FC72C2C362975B4C56CACDE81540C",
        "timestamp": int(time.time()),
    }

    headers = {
        'Content-Type': 'application/json;charset=UTF-8',
        'Accept': 'application/json, text/plain, */*',
        'Authorization':
        'Bearer YOUR_API_TOKEN_HERE'  # Replace with your actual API token
    }

    try:
        response = requests.post(API_URL, headers=headers, json=request_data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return {"error": str(e)}


async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].isdigit():
        last_drawn_number = int(context.args[0])
        user_id = update.message.from_user.id

        if user_id not in user_states:
            user_states[user_id] = {'category': 'BIG', 'last_loss': False}

        if 0 <= last_drawn_number <= 9:
            api_data = await fetch_data()

            if "error" in api_data:
                await update.message.reply_text(
                    f"<b>Error fetching data:</b> {api_data['error']}",
                    parse_mode=ParseMode.HTML)
                return

            await generate_prediction(update, api_data, last_drawn_number,
                                      user_id)
        else:
            await update.message.reply_text(
                "<b>Please provide a valid number between 0 and 9.</b>",
                parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            "<b>Usage:</b> /predict <number> (0-9)", parse_mode=ParseMode.HTML)


async def generate_prediction(update: Update, data: dict,
                              last_drawn_number: int, user_id: int) -> None:
    number_scores = [0] * 10
    drawn_history = [5, 8, 8, 9, 3]  # Example history

    for index, number in enumerate(drawn_history):
        if index < len(drawn_history) - 3:
            number_scores[number] += 1
        else:
            number_scores[number] -= 1

    number_scores[last_drawn_number] += 5

    frequency_data = next(
        (item for item in data['data'] if item['typeName'] == "Frequency"), {})
    missing_data = next(
        (item for item in data['data'] if item['typeName'] == "Missing"), {})

    for i in range(10):
        number_scores[i] += missing_data.get(f'number_{i}', 0) * 2
        number_scores[i] += (10 - frequency_data.get(f'number_{i}', 0))

    ranked_predictions = [{
        'number': i,
        'score': score
    } for i, score in enumerate(number_scores) if score > 0]
    ranked_predictions.sort(key=lambda x: x['score'], reverse=True)
    top_predictions = ranked_predictions[:7]  # Get top 7 numbers

    small_count = sum(1 for pred in top_predictions
                      if 0 <= pred['number'] <= 4)
    big_count = sum(1 for pred in top_predictions if 5 <= pred['number'] <= 9)

    if user_states[user_id]['last_loss']:
        user_states[user_id]['category'] = 'SMALL' if user_states[user_id][
            'category'] == 'BIG' else 'BIG'
        user_states[user_id]['last_loss'] = False
    else:
        user_states[user_id][
            'category'] = 'BIG' if small_count > big_count else 'SMALL'

    category = user_states[user_id]['category']

    output = (
        f"<b>🎯 Prediction Based on Last Number {last_drawn_number}:</b>\n\n"
        f"<b>Top Predicted Numbers:</b>\n")

    for index, pred in enumerate(top_predictions):
        size_label = 'Big' if pred['number'] >= 5 else 'Small'
        output += f"{index + 1}. <b>{pred['number']} ({size_label})</b>\n"

    output += f"\n<b>➡️ Prediction Bet on :</b> {category}"

    keyboard = [[
        InlineKeyboardButton("Win", callback_data=f"win_{user_id}"),
        InlineKeyboardButton("Change Pre🔁", callback_data=f"loss_{user_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(output,
                                    reply_markup=reply_markup,
                                    parse_mode=ParseMode.HTML)


async def button_handler(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = int(query.data.split('_')[1])
    action = query.data.split('_')[0]

    if user_id not in user_states:
        user_states[user_id] = {'category': 'BIG', 'last_loss': False}

    if action == 'win':
        await query.answer("Win, Congratulations 🎉.")
    elif action == 'loss':
        user_states[user_id]['last_loss'] = True
        await query.answer("Next prediction will switch.")


def keep_alive():
    flask_app.run(host='0.0.0.0', port=5000)  # Run Flask app


def run_bot():
    app = ApplicationBuilder().token(
        "7814962462:AAHtlOJ1rdbuXTFw6G8sFTvZx0TuuLcnMqA").build(
        )  # Replace with your actual bot token

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("predict", predict))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()


if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    run_bot()
