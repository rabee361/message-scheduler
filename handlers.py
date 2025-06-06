
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import os
from database import ScheduledMessage , Session
from logger import logger


# Define states for conversation handler
SELECTING_ACTION, TYPING_CHAT_MESSAGE, TYPING_USER_MESSAGE, SELECTING_DAY, TYPING_HOUR, TYPING_MINUTE, SELECTING_TARGET, TEST_ACTION = range(8)



async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test the bot to check if it's running"""
    await update.message.reply_text(
        "Welcome to the Message Scheduler Bot! What would you like to do?",
    )
    return TEST_ACTION


# Helper functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user what they want to do."""
    keyboard = [
        [InlineKeyboardButton("Schedule a new message for a friend", callback_data="schedule")],
        [InlineKeyboardButton("Schedule a new message for me", callback_data="schedule_for_me")],
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
        return TYPING_CHAT_MESSAGE
    if query.data == "schedule_for_me":
        context.user_data["is_self_message"] = True
        await query.edit_message_text(text="Please enter the message you want to schedule for yourself:")
        return TYPING_USER_MESSAGE
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
        
        # Ask for hour input
        await query.edit_message_text(
            text=f"Selected day: {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day]}.\n\nPlease enter an hour (0-23):"
        )
        return TYPING_HOUR


async def hour_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process hour input and ask for minute."""
    try:
        hour = int(update.message.text.strip())
        if 0 <= hour <= 23:
            context.user_data["hour"] = hour
            await update.message.reply_text(
                f"Selected hour: {hour}\n\nPlease enter a minute (0-59):"
            )
            return TYPING_MINUTE
        else:
            await update.message.reply_text(
                "⚠️ Invalid hour. Please enter a number between 0 and 23:"
            )
            return TYPING_HOUR
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid input. Please enter a number between 0 and 23:"
        )
        return TYPING_HOUR


async def minute_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process minute input and continue the flow."""
    try:
        minute = int(update.message.text.strip())
        if 0 <= minute <= 59:
            context.user_data["minute"] = minute
            
            await update.message.reply_text(
                f"Selected time: {context.user_data['hour']:02d}:{minute:02d}\n\n"
                "Please forward a message from the target chat/group or send the chat ID where you want to schedule the message.\n\n"
                "⚠️ IMPORTANT: Before scheduling, make sure the bot has access to the target chat:\n"
                "• For private chats: The user must start a chat with this bot\n"
                "• For groups: Add this bot as a member to the group\n"
                "• For channels: Add this bot as an administrator of the channel"
            )
            return SELECTING_TARGET
        else:
            await update.message.reply_text(
                "⚠️ Invalid minute. Please enter a number between 0 and 59:"
            )
            return TYPING_MINUTE
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid input. Please enter a number between 0 and 59:"
        )
        return TYPING_MINUTE


async def chat_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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



async def user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    
    # Check if this is a self-message (from schedule_for_me flow)
    if context.user_data.get("is_self_message", False):
        target_chat_id = update.effective_user.id
        target_chat_title = "Yourself"
    # Check if it's a forwarded message
    elif hasattr(update.message, 'forward_origin') and update.message.forward_origin and hasattr(update.message.forward_origin, 'sender_user') and update.message.forward_origin.sender_user and hasattr(update.message.forward_origin.sender_user, 'id'):
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


async def test_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test the job queue by scheduling a message to be sent in 30 seconds."""
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("Scheduling a test message to be sent in 30 seconds...")
    
    # Schedule a job to run once after 30 seconds
    context.application.job_queue.run_once(
        callback=test_job_callback,
        when=30,
        data={
            "chat_id": chat_id,
            "message": "This is a test message from the job queue! If you see this, your job queue is working correctly."
        }
    )
    
    # Show all active jobs
    jobs = context.application.job_queue.jobs()
    job_names = [job.name or "unnamed" for job in jobs]
    await update.message.reply_text(f"Currently scheduled jobs: {len(jobs)}\n{', '.join(job_names)}")


async def test_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback function for the test job."""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message = job_data["message"]
    
    logger.info(f"Executing test job callback for chat {chat_id}")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=message
    )
    
    logger.info(f"Test message successfully sent to {chat_id}")
