import logging
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from telegram.ext import JobQueue, PicklePersistence
from sqlalchemy import create_engine, Column, Integer, String, Text, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///schedule_bot.db')
Session = sessionmaker(bind=engine)

# Define states for conversation handler
SELECTING_ACTION, TYPING_MESSAGE, SELECTING_DAY, SELECTING_HOUR, SELECTING_MINUTE, SELECTING_TARGET = range(6)

# Model for scheduled messages
class ScheduledMessage(Base):
    __tablename__ = 'scheduled_messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    chat_id = Column(Integer)
    message_text = Column(Text)
    day_of_week = Column(Integer)  # 0-6 (Monday-Sunday)
    time = Column(Time)
    target_chat_id = Column(String)
    target_chat_title = Column(String)

# Create tables
Base.metadata.create_all(engine)

# Helper functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user what they want to do."""
    keyboard = [
        [InlineKeyboardButton("Schedule a new message", callback_data="schedule")],
        [InlineKeyboardButton("List scheduled messages", callback_data="list")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to the Message Scheduler Bot! What would you like to do?",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "schedule":
        await query.edit_message_text(text="Please enter the message you want to schedule:")
        return TYPING_MESSAGE
    elif query.data == "list":
        await list_scheduled_messages(update, context)
        return ConversationHandler.END
    elif query.data == "cancel":
        await query.edit_message_text(text="Operation cancelled.")
        return ConversationHandler.END
    
    # Day selection
    elif query.data.startswith("day_"):
        day = int(query.data.split("_")[1])
        context.user_data["day"] = day
        
        # Ask for hour
        keyboard = [[InlineKeyboardButton(str(i), callback_data=f"hour_{i}") for i in range(0, 24, 4)]]
        keyboard.append([InlineKeyboardButton(str(i), callback_data=f"hour_{i}") for i in range(1, 24, 4)])
        keyboard.append([InlineKeyboardButton(str(i), callback_data=f"hour_{i}") for i in range(2, 24, 4)])
        keyboard.append([InlineKeyboardButton(str(i), callback_data=f"hour_{i}") for i in range(3, 24, 4)])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"Selected day: {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day]}. Now select the hour:",
            reply_markup=reply_markup
        )
        return SELECTING_HOUR
    
    # Hour selection
    elif query.data.startswith("hour_"):
        hour = int(query.data.split("_")[1])
        context.user_data["hour"] = hour
        
        # Ask for minute
        keyboard = [
            [InlineKeyboardButton("00", callback_data="minute_0"), 
             InlineKeyboardButton("15", callback_data="minute_15"),
             InlineKeyboardButton("30", callback_data="minute_30"),
             InlineKeyboardButton("45", callback_data="minute_45")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"Selected time: {hour}:XX. Now select the minute:",
            reply_markup=reply_markup
        )
        return SELECTING_MINUTE
    
    # Minute selection
    elif query.data.startswith("minute_"):
        minute = int(query.data.split("_")[1])
        context.user_data["minute"] = minute
        
        await query.edit_message_text(
            text="Please forward a message from the target chat/group or send the chat ID where you want to schedule the message.\n\n"
                 "⚠️ IMPORTANT: Before scheduling, make sure the bot has access to the target chat:\n"
                 "• For private chats: The user must start a chat with this bot\n"
                 "• For groups: Add this bot as a member to the group\n"
                 "• For channels: Add this bot as an administrator of the channel"
        )
        return SELECTING_TARGET

async def message_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store message text and ask for day."""
    context.user_data["message"] = update.message.text
    
    # Ask for day of week
    keyboard = [
        [InlineKeyboardButton("Monday", callback_data="day_0"),
         InlineKeyboardButton("Tuesday", callback_data="day_1"),
         InlineKeyboardButton("Wednesday", callback_data="day_2")],
        [InlineKeyboardButton("Thursday", callback_data="day_3"),
         InlineKeyboardButton("Friday", callback_data="day_4")],
        [InlineKeyboardButton("Saturday", callback_data="day_5"),
         InlineKeyboardButton("Sunday", callback_data="day_6")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please select the day of the week for your scheduled message:",
        reply_markup=reply_markup
    )
    return SELECTING_DAY

async def target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store target chat and schedule the message."""
    target_chat_id = None
    target_chat_title = None
    
    # Check if it's a forwarded message
    if update.message.forward_origin.sender_user.id:
        target_chat_id = update.message.forward_origin.sender_user.id
        target_chat_title = str(update.message.forward_origin.sender_user.id) or "Private Chat"
    # Or if user sent a chat ID directly
    elif update.message.text and update.message.text.strip('-').isdigit():
        target_chat_id = update.message.text
        target_chat_title = "Custom Chat ID"
    # Check if user typed "yes" to confirm scheduling despite test error
    elif update.message.text and update.message.text.lower() == "yes" and "pending_message" in context.user_data:
        # Retrieve the pending message details
        pending = context.user_data["pending_message"]
        message_id = pending["message_id"]
        target_chat_title = pending["target_chat_title"]
        
        # Schedule the message and clean up
        try:
            await schedule_new_message(update, context, message_id)
        except Exception as e:
            logger.error(f"Error scheduling message: {str(e)}")
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        await update.message.reply_text(
            f"✅ Message scheduled successfully!\n"
            f"It will be sent every {day_names[pending['day_of_week']]} at {pending['time'].hour:02d}:{pending['time'].minute:02d} "
            f"to {target_chat_title}."
        )
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("I couldn't identify a target chat. Please forward a message from a chat or send a numeric chat ID.")
        return SELECTING_TARGET
    
    # Store everything in the database
    session = Session()
    scheduled_time = time(hour=context.user_data["hour"], minute=context.user_data["minute"])
    
    new_message = ScheduledMessage(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        message_text=context.user_data["message"],
        day_of_week=context.user_data["day"],
        time=scheduled_time,
        target_chat_id=str(target_chat_id),
        target_chat_title=target_chat_title
    )
    
    session.add(new_message)
    session.commit()
    message_id = new_message.id
    session.close()
    
    # Send a test message first
    try:
        await update.message.reply_text("Sending test message to the target chat...")
        
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=f"TEST MESSAGE: {context.user_data['message']}\n\nThis is a test. This message will be sent automatically every " + 
                 f"{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][context.user_data['day']]} " +
                 f"at {context.user_data['hour']:02d}:{context.user_data['minute']:02d}."
        )
        
        await update.message.reply_text("✅ Test message sent successfully!")
        
        # Schedule the message using the application's job queue
        try:
            await schedule_new_message(update, context, message_id)
        except Exception as e:
            logger.error(f"Error scheduling message: {str(e)}")
            # Even if scheduling fails, the message is still in the database
            # and will be scheduled next time the bot restarts
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        await update.message.reply_text(
            f"✅ Message scheduled successfully!\n"
            f"It will be sent every {day_names[context.user_data['day']]} at {context.user_data['hour']:02d}:{context.user_data['minute']:02d} "
            f"to {target_chat_title}."
        )
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        error_message = str(e)
        access_instructions = (
            "To give the bot access to the target chat:\n"
            "• For private chats: The user must start a chat with this bot\n"
            "• For groups: Add this bot as a member to the group\n"
            "• For channels: Add this bot as an administrator of the channel\n\n"
            "Would you like to proceed with scheduling anyway? Use /start to try again or type 'yes' to continue."
        )
        
        await update.message.reply_text(
            f"❌ Failed to send test message: {error_message}\n\n"
            f"{access_instructions}"
        )
        logger.error(f"Error sending test message: {error_message}")
        
        # Wait for user confirmation before proceeding
        context.user_data["pending_message"] = {
            "user_id": update.effective_user.id,
            "chat_id": update.effective_chat.id,
            "message_text": context.user_data["message"],
            "day_of_week": context.user_data["day"],
            "time": scheduled_time,
            "target_chat_id": str(target_chat_id),
            "target_chat_title": target_chat_title,
            "message_id": message_id
        }
        return SELECTING_TARGET

async def list_scheduled_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled messages for the user."""
    user_id = update.effective_user.id
    session = Session()
    messages = session.query(ScheduledMessage).filter_by(user_id=user_id).all()
    
    if not messages:
        if update.callback_query:
            await update.callback_query.edit_message_text("You don't have any scheduled messages.")
        else:
            await update.message.reply_text("You don't have any scheduled messages.")
        session.close()
        return
    
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    response = "Your scheduled messages:\n\n"
    
    for msg in messages:
        time_str = msg.time.strftime("%H:%M")
        response += f"ID: {msg.id}\n"
        response += f"Day: {day_names[msg.day_of_week]}\n"
        response += f"Time: {time_str}\n"
        response += f"Target: {msg.target_chat_title}\n"
        response += f"Message: {msg.message_text[:50]}{'...' if len(msg.message_text) > 50 else ''}\n\n"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(response)
    else:
        await update.message.reply_text(response)
    
    session.close()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the scheduled message."""
    job = context.job
    message_id = job.data["message_id"]
    
    session = Session()
    message = session.query(ScheduledMessage).filter_by(id=message_id).first()
    
    if message:
        try:
            # Send the message to the target chat
            await context.bot.send_message(
                chat_id=message.target_chat_id,
                text=message.message_text
            )
            
            # Notify the user that the message was sent
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"✅ Your scheduled message (ID: {message_id}) has been sent to {message.target_chat_title}."
            )
        except Exception as e:
            # Notify the user if there was an error
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"❌ Failed to send your scheduled message (ID: {message_id}): {str(e)}"
            )
    
    session.close()

async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a scheduled message."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a valid message ID to delete. Example: /delete 1")
        return
    
    message_id = int(context.args[0])
    user_id = update.effective_user.id
    
    session = Session()
    message = session.query(ScheduledMessage).filter_by(id=message_id, user_id=user_id).first()
    
    if not message:
        await update.message.reply_text(f"No message found with ID {message_id} or you don't have permission to delete it.")
        session.close()
        return
    
    # Remove job if it exists
    job_name = f"message_{message_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # Delete from database
    session.delete(message)
    session.commit()
    session.close()
    
    await update.message.reply_text(f"Message with ID {message_id} has been deleted.")

async def schedule_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    """Schedule a newly created message using application's job queue."""
    session = Session()
    message = session.query(ScheduledMessage).filter_by(id=message_id).first()
    
    if message and context.application.job_queue:
        scheduled_time = time(hour=message.time.hour, minute=message.time.minute)
        job_name = f"message_{message.id}"
        
        # Add the job to the queue
        context.application.job_queue.run_daily(
            send_scheduled_message,
            time=scheduled_time,
            days=(message.day_of_week,),
            name=job_name,
            chat_id=message.chat_id,
            user_id=message.user_id,
            data={"message_id": message.id}
        )
        
        logger.info(f"Scheduled message {message_id} to run daily at {scheduled_time} on day {message.day_of_week}")
    else:
        logger.error(f"Failed to schedule message {message_id}. Job queue: {context.application.job_queue}")
    
    session.close()

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
            TYPING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_text_handler)],
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

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
