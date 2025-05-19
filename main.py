import logging
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from telegram.ext import JobQueue, PicklePersistence
from database import create_tables , ScheduledMessage , Session
import os
from handlers import *





# Define states for conversation handler
SELECTING_ACTION, TYPING_CHAT_MESSAGE, TYPING_USER_MESSAGE, SELECTING_DAY, SELECTING_HOUR, SELECTING_MINUTE, SELECTING_TARGET = range(7)


create_tables()



def main() -> None:
    """Start the bot."""
    # Create persistence directory if it doesn't exist
    if not os.path.exists("data"):
        os.makedirs("data")
    
    # Set up persistence for data storage
    persistence = PicklePersistence(filepath="data/bot_data")
    
    # Create the Application with job queue and persistence
    application = Application.builder().token("8132807917:AAEARxy2iaVL00fumaozT2-mh81Ye0T0I0Y").persistence(persistence).build()
    
    # Get the job queue (should be properly initialized now)
    job_queue = application.job_queue
    
    # Schedule all existing messages in the database
    if job_queue:
        session = Session()
        messages = session.query(ScheduledMessage).all()
        for message in messages:
            scheduled_time = time(hour=message.time.hour, minute=message.time.minute)
            job_name = f"message_{message.id}"
            job_queue.run_daily(
                send_scheduled_message,
                time=scheduled_time,
                days=(message.day_of_week,),
                name=job_name,
                chat_id=message.chat_id,
                user_id=message.user_id,
                data={"message_id": message.id}
            )
        session.close()
    else:
        logging.error("Job queue is not initialized!")
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [CallbackQueryHandler(button_handler)],
            TYPING_CHAT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message_handler)],
            TYPING_USER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_message_handler)],
            SELECTING_DAY: [CallbackQueryHandler(button_handler)],
            SELECTING_HOUR: [CallbackQueryHandler(button_handler)],
            SELECTING_MINUTE: [CallbackQueryHandler(button_handler)],
            SELECTING_TARGET: [MessageHandler(filters.ALL & ~filters.COMMAND, target_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("list", list_scheduled_messages))
    application.add_handler(CommandHandler("delete", delete_message))
    application.add_handler(CommandHandler("test", test))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
