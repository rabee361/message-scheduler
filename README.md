# Telegram Message Scheduler Bot

A Telegram bot that allows users to schedule recurring messages to be sent weekly at a specific day and time.

## Features

- Schedule messages to be sent weekly on a specific day and time
- Choose target chats/groups to send messages to
- List all scheduled messages
- Delete scheduled messages

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Get a Telegram Bot token from [BotFather](https://t.me/botfather)
4. Open `main.py` and replace `"YOUR_BOT_TOKEN"` with your actual bot token
5. Run the bot:
   ```
   python main.py
   ```

## Usage

1. Start a chat with your bot and send the `/start` command
2. Select "Schedule a new message" from the menu
3. Enter the message you want to schedule
4. Select the day of the week
5. Select the hour and minute
6. Forward a message from the target chat/group or send the chat ID
7. Your message is now scheduled!

### Available Commands

- `/start` - Start the bot and show the main menu
- `/list` - List all your scheduled messages
- `/delete <id>` - Delete a scheduled message by its ID
- `/cancel` - Cancel the current operation

## Database

The bot uses SQLite with SQLAlchemy for storing scheduled messages. The database file `schedule_bot.db` will be created automatically in the same directory as the script.

## Notes

- To schedule messages to a chat/group, the bot must be a member of that chat/group
- For private chats, the user must have started a conversation with the bot
- For channels, the bot must be an administrator 