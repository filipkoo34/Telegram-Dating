import logging
import aiosqlite
from telegram import __version__ as TG_VER

# Ensure compatibility with the latest version of python-telegram-bot
try:
    from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext
except ImportError:
    from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, Filters as filters, ConversationHandler, CallbackContext

GENDER, AGE, HOBBY, LOCATION, PHOTO, DESCRIPTION, MATCHING, EDIT_PROFILE_DESCRIPTION = range(8)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def get_db_connection():
    try:
        return await aiosqlite.connect('database.db')
    except aiosqlite.Error as e:
        logging.error(f"Error connecting to database: {e}")
        return None

async def user_already_registered(user_id):
    conn = await get_db_connection()
    if not conn:
        return False
    async with conn:
        async with conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            user_exists = await cursor.fetchone() is not None
    return user_exists

def restricted(func):
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if not await user_already_registered(user_id):
            await update.message.reply_text("Sorry, you are not registered yet. Please start by /start.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if await user_already_registered(user_id):
        await update.message.reply_text("Welcome back! You are already registered.")
    else:
        reply_keyboard = [[KeyboardButton('Pria'), KeyboardButton('Wanita')]]
        await update.message.reply_text(
            'Hello! Please select your gender.',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return GENDER

async def gender(update: Update, context: CallbackContext):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text('How old are you?')
    return AGE

async def age(update: Update, context: CallbackContext):
    try:
        age = int(update.message.text)
        if age <= 0:
            raise ValueError("Umur harus lebih besar dari 0.")
        context.user_data['age'] = age
        await update.message.reply_text('What are your hobbies?')
        return HOBBY
    except ValueError:
        await update.message.reply_text('Please enter a valid age.')
        return AGE

async def hobby(update: Update, context: CallbackContext):
    context.user_data['hobby'] = update.message.text
    await update.message.reply_text('Where are you located? Please send your current location.')
    return LOCATION

async def location(update: Update, context: CallbackContext):
    location = update.message.location
    if not location:
        await update.message.reply_text('Invalid location. Please submit your location.')
        return LOCATION
    context.user_data['location'] = (location.latitude, location.longitude)
    await update.message.reply_text('Thank you! Please upload your profile photo now.')
    return PHOTO

async def photo(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"profile_photos/{user_id}.jpg"
    await photo_file.download(photo_path)
    context.user_data['photo_path'] = photo_path
    await update.message.reply_text('Your profile photo has been uploaded. Please add your profile description now.')
    return DESCRIPTION

async def description(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    context.user_data['description'] = update.message.text

    user_data = {
        'user_id': user_id,
        'gender': context.user_data['gender'],
        'age': context.user_data['age'],
        'hobby': context.user_data['hobby'],
        'location': context.user_data['location'],
        'photo_path': context.user_data['photo_path'],
        'description': context.user_data['description']
    }
    await save_user_data(user_data)

    await update.message.reply_text('Your profile description has been added. Your profile has been saved.')
    await update.message.reply_text('Start looking for a partner?', reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Yes'), KeyboardButton('No')]], one_time_keyboard=True))
    return MATCHING

async def save_user_data(user_data):
    conn = await get_db_connection()
    if not conn:
        return
    async with conn:
        await conn.execute("""
            INSERT INTO users (user_id, gender, age, hobby, location, photo_path, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_data['user_id'], user_data['gender'], user_data['age'], user_data['hobby'], str(user_data['location']), user_data['photo_path'], user_data['description']))
        await conn.commit()

async def start_matching(update: Update, context: CallbackContext):
    reply_keyboard = [[KeyboardButton("Like"), KeyboardButton("Don't like")]]
    await update.message.reply_text(
        'I have found a potential match for you. Are you interested?',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return MATCHING

async def choose_matching(update: Update, context: CallbackContext):
    choice = update.message.text
    if choice not in ['Like', 'Don't like']:
        await update.message.reply_text('Invalid selection. Please select “Like” or “Dislike”.')
        return MATCHING

    if choice == 'Suka':
        await update.message.reply_text('You like this couple! Congratulations!')
    else:
        await update.message.reply_text('You are not interested in this match. Try another one!')

    await update.message.reply_text('Do you want to find a partner again?', reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Yes'), KeyboardButton('No')]], one_time_keyboard=True))
    return MATCHING

async def view_profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    profile_data = await get_user_profile(user_id)
    if profile_data:
        await update.message.reply_text(f"Profil Anda:\n{profile_data}")
    else:
        await update.message.reply_text("Your profile is empty.")

async def get_user_profile(user_id):
    conn = await get_db_connection()
    if not conn:
        return None
    async with conn:
        async with conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            user_profile = await cursor.fetchone()
    return user_profile

@restricted
async def edit_profile(update: Update, context: CallbackContext):
    await update.message.reply_text("Please add your profile information.")
    return EDIT_PROFILE_DESCRIPTION

async def save_profile_description(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    profile_description = update.message.text
    context.user_data['description'] = profile_description

    conn = await get_db_connection()
    if not conn:
        return
    async with conn:
        await conn.execute("UPDATE users SET description=? WHERE user_id=?", (profile_description, user_id))
        await conn.commit()

    await update.message.reply_text("Your profile description has been updated.")

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text('The process has been canceled. See you later!')
    return ConversationHandler.END

if __name__ == '__main__':
    import asyncio
    async def setup_db():
        conn = await get_db_connection()
        if conn:
            async with conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        gender TEXT,
                        age INTEGER,
                        hobby TEXT,
                        location TEXT,
                        photo_path TEXT,
                        description TEXT,
                        registration_date DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                await conn.commit()

    asyncio.run(setup_db())

    application = Application.builder().token('8396210059:AAHhRcLU9S84glkAojFTq5sRWAGmGB0z228').build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            HOBBY: [MessageHandler(filters.TEXT & ~filters.COMMAND, hobby)],
            LOCATION: [MessageHandler(filters.LOCATION, location)],
            PHOTO: [MessageHandler(filters.PHOTO, photo)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            MATCHING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_matching)],
            EDIT_PROFILE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_description)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    application.run_polling()
