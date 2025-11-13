import { Server as SocketIOServer } from 'socket.io';
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  AnyMessageContent,
  WASocket,
  BaileysEventMap,
  ConnectionState
} from '../index';
import axios from 'axios';
import { Boom } from '@hapi/boom';
import QRCode from 'qrcode';
import { join } from 'path';
import { existsSync, mkdirSync, rmSync } from 'fs';
import { logger, whatsappLogger } from '../Utils/apiLogger';
import { DatabaseService } from './DatabaseService';
import { WebhookService } from './WebhookService';
import { WhatsAppSession, SessionStatus } from '../Types/api';


export class WhatsAppService {
  private sessions: Map<string, WhatsAppSession> = new Map();
  private io: SocketIOServer;
  private dbService: DatabaseService;
  private webhookService: WebhookService;

  constructor(io: SocketIOServer) {
    this.io = io;
    this.dbService = new DatabaseService();
    this.webhookService = new WebhookService();

    // Ensure auth directory exists
    const authDir = join(process.cwd(), 'auth_sessions');
    if (!existsSync(authDir)) {
      mkdirSync(authDir, { recursive: true });
    }

    // Restore sessions when service is initialized
    this.restoreSessions();
  }

  /**
   * Restore all sessions from database on server startup
   */
  private async restoreSessions(): Promise<void> {
    try {
      const sessions = await this.dbService.client.session.findMany();
      whatsappLogger.info(`Found ${sessions.length} sessions to restore`);

      for (const session of sessions) {
        try {
          // Only restore sessions that were connected or in a state that suggests they should reconnect
          if (session.status === 'CONNECTED' || session.status === 'CONNECTING' || session.status === 'PAIRING_REQUIRED') {
            // Create a session object without DB record (since it already exists)
            await this.createSessionWithoutDBRecord(session.sessionId, session.userId);
            whatsappLogger.info(`Restored session ${session.sessionId}`);
          }
        } catch (error) {
          whatsappLogger.error(`Failed to restore session ${session.sessionId}:`, error);
        }
      }
    } catch (error) {
      whatsappLogger.error('Failed to restore sessions:', error);
    }
  }

  async createSession(sessionId: string, workflowId : string = '', userId: string, usePairingCode = false): Promise<WhatsAppSession> {
    try {
      if (this.sessions.has(sessionId)) {
        throw new Error('Session already exists');
      }

      // Create session record in database
      await this.dbService.createSession({
        sessionId,
        workflowId,
        userId
      });

      const session: WhatsAppSession = {
        id: sessionId,
        socket: null,
        status: SessionStatus.CONNECTING,
        lastSeen: new Date()
      };

      this.sessions.set(sessionId, session);

      // Initialize WhatsApp connection
      await this.initializeWhatsAppConnection(sessionId, usePairingCode);

      return session;
    } catch (error) {
      whatsappLogger.error(`Failed to create session ${sessionId}:`, error);
      throw error;
    }
  }

  async createSessionWithoutDBRecord(sessionId: string, userId: string, usePairingCode = false): Promise<WhatsAppSession> {
    try {
      if (this.sessions.has(sessionId)) {
        throw new Error('Session already exists');
      }

      const session: WhatsAppSession = {
        id: sessionId,
        socket: null,
        status: SessionStatus.CONNECTING,
        lastSeen: new Date()
      };

      this.sessions.set(sessionId, session);

      // Initialize WhatsApp connection
      await this.initializeWhatsAppConnection(sessionId, usePairingCode);

      return session;
    } catch (error) {
      whatsappLogger.error(`Failed to create session instance ${sessionId}:`, error);
      throw error;
    }
  }

  private async initializeWhatsAppConnection(sessionId: string, usePairingCode = false) {
    try {
      const authDir = join(process.cwd(), 'auth_sessions', sessionId);
      const { state, saveCreds } = await useMultiFileAuthState(authDir);
      const { version } = await fetchLatestBaileysVersion();

      const socket = makeWASocket({
        version,
        logger: whatsappLogger,
        printQRInTerminal: false,
        auth: {
          creds: state.creds,
          keys: makeCacheableSignalKeyStore(state.keys, whatsappLogger)
        },
        generateHighQualityLinkPreview: true,
        getMessage: async (key) => {
          // Implement message retrieval from database
          return undefined;
        }
      });

      const session = this.sessions.get(sessionId)!;
      session.socket = socket;
      
      // Handle connection events
      socket.ev.on('connection.update', async (update) => {
        await this.handleConnectionUpdate(sessionId, update);
      });

      // Handle credentials update
      socket.ev.on('creds.update', saveCreds);

      // Handle messages 
      socket.ev.on('messages.upsert', async (messageUpdate) => { 
      await this.handleMessagesUpsert(sessionId, messageUpdate); 
      });

      // // Handle message updates (read receipts, etc.)
      // socket.ev.on('messages.update', async (messageUpdates) => {
      //   await this.handleMessagesUpdate(sessionId, messageUpdates);
      // });

      // Handle chats
      socket.ev.on('chats.upsert', async (chats) => {
        await this.handleChatsUpsert(sessionId, chats);
      });

      // Handle contacts
      socket.ev.on('contacts.upsert', async (contacts) => {
        await this.handleContactsUpsert(sessionId, contacts);
      });

      // Handle groups
      socket.ev.on('groups.upsert', async (groups) => {
        await this.handleGroupsUpsert(sessionId, groups);
      });

      // Handle pairing code if requested
      if (usePairingCode && !socket.authState.creds.registered) {
        session.status = SessionStatus.PAIRING_REQUIRED;
        await this.updateSessionInDatabase(sessionId, { status: 'PAIRING_REQUIRED' });
        this.emitSessionUpdate(sessionId);
      }

    } catch (error) {
      whatsappLogger.error(`Failed to initialize WhatsApp connection for ${sessionId}:`, error);
      const session = this.sessions.get(sessionId);
      if (session) {
        session.status = SessionStatus.ERROR;
        await this.updateSessionInDatabase(sessionId, { status: 'ERROR' });
        this.emitSessionUpdate(sessionId);
      }
      throw error;
    }
  }

  private async handleConnectionUpdate(sessionId: string, update: Partial<ConnectionState>) {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    const { connection, lastDisconnect, qr } = update;

    whatsappLogger.info(`Connection update for ${sessionId}:`, { connection, lastDisconnect: lastDisconnect?.error?.message });

    if (qr) {
      // Generate QR code
      try {
        const qrCodeDataURL = await QRCode.toDataURL(qr);
        session.qrCode = qrCodeDataURL;
        session.status = SessionStatus.QR_REQUIRED;
        await this.updateSessionInDatabase(sessionId, {
          status: 'QR_REQUIRED',
          qrCode: qrCodeDataURL
        });
        this.emitSessionUpdate(sessionId);
      } catch (error) {
        whatsappLogger.error(`Failed to generate QR code for ${sessionId}:`, error);
      }
    }

    if (connection === 'close') {
      const shouldReconnect = (lastDisconnect?.error as Boom)?.output?.statusCode !== DisconnectReason.loggedOut;

      if (shouldReconnect) {
        whatsappLogger.info(`Reconnecting session ${sessionId}`);
        session.status = SessionStatus.CONNECTING;
        await this.updateSessionInDatabase(sessionId, { status: 'CONNECTING' });
        this.emitSessionUpdate(sessionId);

        // Reconnect after a delay
        setTimeout(() => {
          this.initializeWhatsAppConnection(sessionId);
        }, 5000);
      } else {
        whatsappLogger.info(`Session ${sessionId} logged out`);
        session.status = SessionStatus.DISCONNECTED;
        await this.updateSessionInDatabase(sessionId, { status: 'DISCONNECTED' });
        this.emitSessionUpdate(sessionId);
      }
    } else if (connection === 'open') {
      whatsappLogger.info(`Session ${sessionId} connected`);
      session.status = SessionStatus.CONNECTED;
      session.lastSeen = new Date();
      session.qrCode = undefined;
      session.pairingCode = undefined;

      // Get user info
      const user = session.socket?.user;
      if (user) {
        session.phoneNumber = user.id.split(':')[0];
        session.name = user.name;
      }

      await this.updateSessionInDatabase(sessionId, {
        status: 'CONNECTED',
        phoneNumber: session.phoneNumber,
        name: session.name,
        lastSeen: session.lastSeen,
        qrCode: null
      });

      this.emitSessionUpdate(sessionId);
    }
  }

  private async handleMessagesUpsert(sessionId: string, messageUpdate: any) {
    const { messages, type } = messageUpdate;

    for (const message of messages) {
      try {
        const session = await this.dbService.getSession(sessionId);

        if (session) {
          // Check if message already exists to prevent duplicate processing
          const existingMessage = await this.dbService.client.message.findUnique({
            where: {
              sessionId_messageId: {
                sessionId: session.id,
                messageId: message.key.id!
              }
            }
          });

          // Skip processing if message already exists
          if (existingMessage) {
            whatsappLogger.info(`Skipping duplicate message ${message.key.id} for session ${sessionId}`);
            continue;
          }
          
          // Handle location messages
          if (message.message?.locationMessage) {
            try {
              const location = message.message.locationMessage;
              const latitude = location.degreesLatitude;
              const longitude = location.degreesLongitude;
              
              whatsappLogger.info('Location message received:', { latitude, longitude });
              
              // Get area information from coordinates using Nominatim API
              const nominatimUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`;
              
              const response = await axios.get(nominatimUrl, {
                headers: {
                  'User-Agent': 'Lynxon-WhatsApp-Bot/1.0'
                },
                timeout: 10000
              });
              
              let formattedAddress = 'Unknown location';
              
              if (response.data && response.data.address) {
                const address = response.data.address;
                
                // Build area description
                let areaInfo: string[] = [];
                
                if (address.road) areaInfo.push(address.road);
                if (address.suburb || address.neighbourhood) {
                  areaInfo.push(address.suburb || address.neighbourhood);
                }
                if (address.city || address.town || address.village) {
                  areaInfo.push(address.city || address.town || address.village);
                }
                if (address.state) areaInfo.push(address.state);
                if (address.country) areaInfo.push(address.country);
                
                formattedAddress = areaInfo.length > 0 ? areaInfo.join(', ') : 'Unknown location';
              }
              
              // Add location info to message metadata
              const locationInfo = {
                latitude,
                longitude,
                formattedAddress,
                name: location.name || null,
                address: response.data?.address || null
              };
              
              // Update the message in database with location info
              await this.dbService.saveMessage({
                messageId: message.key.id!,
                sessionId: session.id,
                chatId: message.key.remoteJid!,
                fromMe: message.key.fromMe || false,
                fromJid: message.key.participant || message.key.remoteJid,
                toJid: message.key.remoteJid!,
                messageType: this.getMessageType(message.message),
                content: {
                  ...message.message,
                  locationInfo
                },
                timestamp: new Date(message.messageTimestamp! * 1000),
                quotedMessage: message.message?.extendedTextMessage?.contextInfo?.quotedMessage ?
                  message.message.extendedTextMessage.contextInfo.stanzaId : undefined,
                metadata: { type, pushName: message.pushName }
              });

              message.message.conversation = formattedAddress;
              
            } catch (locationError) {
              whatsappLogger.error(`Failed to process location for message ${message.key.id}:`, locationError);
            }
          } else {
                await this.dbService.saveMessage({
                messageId: message.key.id!,
                sessionId: session.id,
                chatId: message.key.remoteJid!,
                fromMe: message.key.fromMe || false,
                fromJid: message.key.participant || message.key.remoteJid,
                toJid: message.key.remoteJid!,
                messageType: this.getMessageType(message.message),
                content: message.message,
                timestamp: new Date(message.messageTimestamp! * 1000),
                quotedMessage: message.message?.extendedTextMessage?.contextInfo?.quotedMessage ?
                  message.message.extendedTextMessage.contextInfo.stanzaId : undefined,
                metadata: { type, pushName: message.pushName }
              });

          }
          
            this.io.emit('message', {
              sessionId,
              message,
              type
            });

          // Send webhook only for messages not sent by me
          if (!message.key.fromMe) {
            await this.webhookService.sendWebhook(sessionId, 'message.received', {
              sessionId,
              message,
              type
            });
          }
        }


      } catch (error) {
        whatsappLogger.error(`Failed to handle message for ${sessionId}:`, error);
      }
    }
  }

  private async handleMessagesUpdate(sessionId: string, messageUpdates: any[]) {
    for (const update of messageUpdates) {
      try {
        const { key, update: messageUpdate } = update;

        if (messageUpdate.status) {
          const session = await this.dbService.getSession(sessionId)
          if (session) {
            await this.dbService.updateMessageStatus(
              key.id!,
              session.id,
              messageUpdate.status,
            );
          }
        }

        // Emit to websocket clients
        this.io.emit('messageUpdate', {
          sessionId,
          key,
          update: messageUpdate
        });

      } catch (error) {
        whatsappLogger.error(`Failed to handle message update for ${sessionId}:`, error);
      }
    }
  }

  private async handleChatsUpsert(sessionId: string, chats: any[]) {
    for (const chat of chats) {
      try {
        await this.dbService.upsertChat({
          sessionId,
          jid: chat.id,
          name: chat.name,
          isGroup: chat.id.endsWith('@g.us'),
          isArchived: chat.archived || false,
          isPinned: chat.pinned || false,
          isMuted: chat.mute || false,
          unreadCount: chat.unreadCount || 0,
          lastMessage: chat.lastMessage,
          metadata: chat
        });

        // Emit to websocket clients
        this.io.emit('chatUpdate', {
          sessionId,
          chat
        });

      } catch (error) {
        whatsappLogger.error(`Failed to handle chat upsert for ${sessionId}:`, error);
      }
    }
  }

  private async handleContactsUpsert(sessionId: string, contacts: any[]) {
    for (const contact of contacts) {
      // try {
        // await this.dbService.upsertContact({
        //   sessionId,
        //   jid: contact.id,
        //   name: contact.name,
        //   pushName: contact.notify,
        //   profilePicUrl: contact.imgUrl,
        //   isBlocked: contact.blocked || false,
        //   metadata: contact
        // });

        // Emit to websocket clients
        this.io.emit('contactUpdate', {
          sessionId,
          contact
        });

      // } catch (error) {
      //   whatsappLogger.error(`Failed to handle contact upsert for ${sessionId}:`, error);
      // }
    }
  }

  private async handleGroupsUpsert(sessionId: string, groups: any[]) {
    for (const group of groups) {
      try {
        await this.dbService.client.group.upsert({
          where: {
            sessionId_jid: {
              sessionId,
              jid: group.id
            }
          },
          update: {
            subject: group.subject,
            description: group.desc,
            owner: group.owner,
            participants: group.participants,
            settings: group,
            metadata: group,
            updatedAt: new Date()
          },
          create: {
            sessionId,
            jid: group.id,
            subject: group.subject,
            description: group.desc,
            owner: group.owner,
            participants: group.participants,
            settings: group,
            metadata: group
          }
        });

        // Emit to websocket clients
        this.io.emit('groupUpdate', {
          sessionId,
          group
        });

      } catch (error) {
        whatsappLogger.error(`Failed to handle group upsert for ${sessionId}:`, error);
      }
    }
  }

  private getMessageType(message: any): string {
    if (message?.conversation) return 'TEXT';
    if (message?.extendedTextMessage) return 'TEXT';
    if (message?.imageMessage) return 'IMAGE';
    if (message?.videoMessage) return 'VIDEO';
    if (message?.audioMessage) return 'AUDIO';
    if (message?.documentMessage) return 'DOCUMENT';
    if (message?.stickerMessage) return 'STICKER';
    if (message?.locationMessage) return 'LOCATION';
    if (message?.contactMessage) return 'CONTACT';
    if (message?.pollCreationMessage) return 'POLL';
    if (message?.reactionMessage) return 'REACTION';
    return 'TEXT';
  }

  private async updateSessionInDatabase(sessionId: string, data: any) {
    try {
      await this.dbService.updateSession(sessionId, data);
    } catch (error) {
      whatsappLogger.error(`Failed to update session ${sessionId} in database:`, error);
    }
  }

  private emitSessionUpdate(sessionId: string) {
    const session = this.sessions.get(sessionId);
    if (session) {
      this.io.emit('sessionUpdate', {
        sessionId,
        status: session.status,
        qrCode: session.qrCode,
        pairingCode: session.pairingCode,
        phoneNumber: session.phoneNumber,
        name: session.name,
        lastSeen: session.lastSeen
      });
    }
  }

  // Public methods for API endpoints
  async getSession(sessionId?: string): Promise<WhatsAppSession | undefined> {
    if (sessionId) {
      return this.sessions.get(sessionId);
    }
  }

  async getAllSessions(): Promise<WhatsAppSession[]> {
    return Array.from(this.sessions.values());
  }

  async deleteSession(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session?.socket) {
      try {
        // Check if the socket is in a state where it can be closed
        if (!session.socket.ws.isClosed && !session.socket.ws.isClosing) {
          session.socket.end(undefined);
        }
      } catch (error) {
        // If there's an error closing the socket, log it but continue with cleanup
        whatsappLogger.warn(`Error closing socket for session ${sessionId}:`, error);
      }
    }
    this.sessions.delete(sessionId);
    await this.dbService.deleteSession(sessionId);
  }

  async permanentlyDeleteSession(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session?.socket) {
      try {
        session.socket.end(undefined);
      } catch (error) {
        whatsappLogger.error(`Error ending socket for session ${sessionId}:`, error);
      }
    }
    this.sessions.delete(sessionId);
    
    // Remove authentication files from disk
    try {
      const authDir = join(process.cwd(), 'auth_sessions', sessionId);
      if (existsSync(authDir)) {
        rmSync(authDir, { recursive: true, force: true });
        whatsappLogger.info(`Removed authentication files for session ${sessionId}`);
      }
    } catch (error) {
      whatsappLogger.error(`Error removing authentication files for session ${sessionId}:`, error);
    }
    
    try {
      await this.dbService.permanentlyDeleteSession(sessionId);
    } catch (error) {
      whatsappLogger.error(`Error permanently deleting session ${sessionId} from database:`, error);
      throw error;
    }
  }

  async requestPairingCode(sessionId: string, phoneNumber: string): Promise<string> {
    const session = this.sessions.get(sessionId);
    if (!session?.socket) {
      throw new Error('Session not found or not initialized');
    }

    const code = await session.socket.requestPairingCode(phoneNumber);
    session.pairingCode = code;
    session.phoneNumber = phoneNumber;

    await this.updateSessionInDatabase(sessionId, {
      pairingCode: code,
      phoneNumber
    });

    this.emitSessionUpdate(sessionId);
    return code;
  }

  async sendMessage(sessionId: string, to: string, content: AnyMessageContent): Promise<any> {
    const session = this.sessions.get(sessionId);
    if (!session?.socket) {
      throw new Error('Session not found or not connected');
    }

    if (session.status !== SessionStatus.CONNECTED) {
      throw new Error('Session not connected');
    }

    return await session.socket.sendMessage(to, content);
  }

  async reconnectAllSessions(): Promise<void> {
    try {
      const sessions = await this.dbService.client.session.findMany({
        where: {
          status: 'CONNECTED'
        }
      });

      whatsappLogger.info(`Reconnecting ${sessions.length} sessions`);

      for (const session of sessions) {
        try {
          // Check if session is already in memory
          if (!this.sessions.has(session.sessionId)) {
            // Create a session object without DB record (since it already exists)
            await this.createSessionWithoutDBRecord(session.sessionId, session.userId);
            whatsappLogger.info(`Reconnected session ${session.sessionId}`);
          }
        } catch (error) {
          whatsappLogger.error(`Failed to reconnect session ${session.sessionId}:`, error);
        }
      }
    } catch (error) {
      whatsappLogger.error('Failed to reconnect sessions:', error);
    }
  }

  async shutdown(): Promise<void> {
    logger.info('Shutting down WhatsApp service...');

    for (const [sessionId, session] of this.sessions) {
      if (session.socket) {
        try {
          session.socket.end(undefined);
        } catch (error) {
          whatsappLogger.error(`Error closing session ${sessionId}:`, error);
        }
      }
    }

    this.sessions.clear();
    await this.dbService.disconnect();
    logger.info('WhatsApp service shutdown complete');
  }
}