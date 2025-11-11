# Database Schema Documentation

This document explains the database schema for the Baileys API application.

## Overview

The database uses MySQL as its backend and consists of 9 main tables that store information about users, WhatsApp sessions, messages, chats, contacts, groups, webhooks, webhook deliveries, and API usage.

## Tables

### 1. User

Stores user account information for the API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the user |
| email | String | Unique | User's email address |
| name | String | Nullable | User's name |
| password | String | Required | Hashed user password |
| apiKey | String | Unique, CUID | API key for authentication |
| isActive | Boolean | Default: true | Whether the user account is active |
| role | Role | Default: USER | User role (USER or ADMIN) |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |

Relations:
- Has many Sessions
- Has many Webhooks
- Has many ApiUsage records

### 2. Session

Represents a WhatsApp session/connection.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the session |
| sessionId | String | Unique | WhatsApp session ID |
| phoneNumber | String | Nullable | Phone number associated with session |
| name | String | Nullable | Name of the session |
| status | SessionStatus | Default: DISCONNECTED | Connection status |
| qrCode | String | Nullable | QR code for authentication |
| pairingCode | String | Nullable | Pairing code for authentication |
| lastSeen | DateTime | Nullable | Last time session was active |
| isActive | Boolean | Default: true | Whether session is active |
| authData | Json | Nullable | Authentication data |
| metadata | Json | Nullable | Additional session metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| userId | String | Foreign Key | Reference to User.id |
| workflowId | String | Nullable | n8n workflow (subscription plan) |

Relations:
- Belongs to User
- Has many Messages
- Has many Chats
- Has many Contacts
- Has many Groups

### 3. Message

Stores WhatsApp messages.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the message |
| messageId | String | Required | WhatsApp message ID |
| chatId | String | Required | WhatsApp chat ID |
| fromMe | Boolean | Required | Whether message was sent by user |
| fromJid | String | Nullable | Sender's JID |
| toJid | String | Required | Recipient's JID |
| messageType | MessageType | Required | Type of message |
| content | Json | Required | Message content |
| status | MessageStatus | Default: PENDING | Message delivery status |
| timestamp | DateTime | Required | When message was sent |
| quotedMessage | String | Nullable | ID of quoted message |
| metadata | Json | Nullable | Additional message metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| sessionId | String | Foreign Key | Reference to Session.id |

Constraints:
- Unique combination of sessionId and messageId

### 4. Chat

Stores WhatsApp chat information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the chat |
| jid | String | Required | WhatsApp chat JID |
| name | String | Nullable | Chat name |
| isGroup | Boolean | Default: false | Whether chat is a group |
| isArchived | Boolean | Default: false | Whether chat is archived |
| isPinned | Boolean | Default: false | Whether chat is pinned |
| isMuted | Boolean | Default: false | Whether chat is muted |
| unreadCount | Int | Default: 0 | Number of unread messages |
| lastMessage | Json | Nullable | Last message preview |
| metadata | Json | Nullable | Additional chat metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| sessionId | String | Foreign Key | Reference to Session.id |

Constraints:
- Unique combination of sessionId and jid

### 5. Contact

Stores WhatsApp contact information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the contact |
| jid | String | Required | WhatsApp contact JID |
| name | String | Nullable | Contact name |
| pushName | String | Nullable | Push name |
| profilePicUrl | String | Nullable | Profile picture URL |
| isBlocked | Boolean | Default: false | Whether contact is blocked |
| metadata | Json | Nullable | Additional contact metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| sessionId | String | Foreign Key | Reference to Session.id |

Constraints:
- Unique combination of sessionId and jid

### 6. Group

Stores WhatsApp group information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the group |
| jid | String | Required | WhatsApp group JID |
| subject | String | Nullable | Group subject/name |
| description | String | Nullable | Group description |
| owner | String | Nullable | Group owner JID |
| participants | Json | Nullable | Group participants |
| settings | Json | Nullable | Group settings |
| metadata | Json | Nullable | Additional group metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| sessionId | String | Foreign Key | Reference to Session.id |

Constraints:
- Unique combination of sessionId and jid

### 7. Webhook

Stores webhook configuration for notifying external services.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the webhook |
| url | String | Required | Webhook endpoint URL |
| event | String | Required | Event type to trigger webhook |
| secret | String | Nullable | Secret for signing requests |
| isActive | Boolean | Default: true | Whether webhook is active |
| retries | Int | Default: 0 | Number of retry attempts |
| maxRetries | Int | Default: 3 | Maximum retry attempts |
| lastError | String | Nullable | Last error message |
| metadata | Json | Nullable | Additional webhook metadata |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| userId | String | Foreign Key | Reference to User.id |

Relations:
- Belongs to User
- Has many WebhookDeliveries

### 8. WebhookDelivery

Tracks webhook delivery attempts.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the delivery |
| event | String | Required | Event type |
| payload | Json | Required | Delivery payload |
| status | WebhookStatus | Default: PENDING | Delivery status |
| response | String | Nullable | Response from endpoint |
| attempts | Int | Default: 0 | Number of delivery attempts |
| nextRetry | DateTime | Nullable | Next retry timestamp |
| createdAt | DateTime | Default: now() | Timestamp when record was created |
| updatedAt | DateTime | On update | Timestamp when record was last updated |
| webhookId | String | Foreign Key | Reference to Webhook.id |

Relations:
- Belongs to Webhook

### 9. ApiUsage

Tracks API usage statistics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | Primary Key, CUID | Unique identifier for the usage record |
| endpoint | String | Required | API endpoint |
| method | String | Required | HTTP method |
| status | Int | Required | HTTP status code |
| duration | Int | Required | Request duration in ms |
| timestamp | DateTime | Default: now() | When request was made |
| userId | String | Foreign Key | Reference to User.id |

Relations:
- Belongs to User

## Enums

### Role
- USER
- ADMIN

### SessionStatus
- CONNECTING
- CONNECTED
- DISCONNECTED
- QR_REQUIRED
- PAIRING_REQUIRED
- ERROR

### MessageType
- TEXT
- IMAGE
- VIDEO
- AUDIO
- DOCUMENT
- STICKER
- LOCATION
- CONTACT
- POLL
- REACTION
- BUTTON_REPLY
- LIST_REPLY

### MessageStatus
- PENDING
- SENT
- DELIVERED
- READ
- FAILED

### WebhookStatus
- PENDING
- SUCCESS
- FAILED
- RETRYING