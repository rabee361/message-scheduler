import { Router, Request, Response } from 'express';
import { body, param, query } from 'express-validator';
import { handleValidationErrors, asyncHandler } from '../middleware/errorHandler';
import { sessionMiddleware } from '../middleware/auth';
import { whatsAppService } from '../app';
import { DatabaseService } from '../services/DatabaseService';
import { ApiResponse, SessionStatus, WhatsAppSession, AuthenticatedRequest } from '../Types/api';

const router = Router();
const dbService = new DatabaseService();

// Helper function to serialize session data and remove circular references
function serializeSession(session: WhatsAppSession): any {
  return {
    id: session.id,
    status: session.status,
    qrCode: session.qrCode,
    pairingCode: session.pairingCode,
    phoneNumber: session.phoneNumber,
    name: session.name,
    lastSeen: session.lastSeen,
    authData: session.authData,
    metadata: session.metadata
    // Note: We intentionally exclude the socket property as it contains circular references
  };
}

/**
 * @swagger
 * /api/sessions:
 *   get:
 *     summary: Get all user sessions
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     responses:
 *       200:
 *         description: Sessions retrieved successfully
 */
router.get('/', asyncHandler(async (req: AuthenticatedRequest, res: Response) => {
  const sessions = await dbService.getUserSessions(req.user!.id);

  // Enhance with real-time status from WhatsApp service
  const enhancedSessions = await Promise.all(
    sessions.map(async (session) => {
      const liveSession = await whatsAppService.getSession(session.sessionId);
      return {
        ...session,
        liveStatus: liveSession?.status || SessionStatus.DISCONNECTED,
        qrCode: liveSession?.qrCode,
        pairingCode: liveSession?.pairingCode
      };
    })
  );

  res.json({
    success: true,
    data: enhancedSessions,
    timestamp: new Date().toISOString()
  } as ApiResponse);
}));

/**
 * @swagger
 * /api/sessions:
 *   post:
 *     summary: Create a new WhatsApp session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               sessionId:
 *                 type: string
 *                 description: Unique session identifier
 *               usePairingCode:
 *                 type: boolean
 *                 default: false
 *                 description: Use pairing code instead of QR code
 *     responses:
 *       201:
 *         description: Session created successfully
 *       400:
 *         description: Session already exists
 */
router.post('/', [
  body('sessionId').notEmpty().trim().isLength({ min: 1, max: 50 }),
  body('usePairingCode').optional().isBoolean()
], handleValidationErrors, asyncHandler(async (req: AuthenticatedRequest, res: Response) => {
  const { sessionId, workflowId, usePairingCode = false } = req.body;

  // Check if session already exists
  const existingSession = await dbService.getSession(sessionId);
  if (existingSession) {
    return res.status(400).json({
      success: false,
      error: 'Session already exists',
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }

  // Create session
  const session = await whatsAppService.createSession(sessionId, workflowId, req.user!.id, usePairingCode);

  res.status(201).json({
    success: true,
    data: serializeSession(session),
    message: 'Session created successfully',
    timestamp: new Date().toISOString()
  } as ApiResponse);
}));

/**
 * @swagger
 * /api/sessions/{sessionId}:
 *   get:
 *     summary: Get session details
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Session details retrieved successfully
 *       404:
 *         description: Session not found
 */
router.get('/:sessionId', [
  param('sessionId').notEmpty()
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req: AuthenticatedRequest, res: Response) => {
  const { sessionId } = req.params;

  if (sessionId) {
    const dbSession = await dbService.getSession(sessionId);
    const liveSession = await whatsAppService.getSession(sessionId);
  
    if (!dbSession) {
      return res.status(404).json({
        success: false,
        error: 'Session not found',
        timestamp: new Date().toISOString()
      } as ApiResponse);
    }
  
    const sessionData = {
      ...dbSession,
      liveStatus: liveSession?.status || SessionStatus.DISCONNECTED,
      qrCode: liveSession?.qrCode,
      pairingCode: liveSession?.pairingCode
    };
  
    res.json({
      success: true,
      data: sessionData,
      timestamp: new Date().toISOString()
    } as ApiResponse);

  }
}));

/**
 * @swagger
 * /api/sessions/{sessionId}:
 *   delete:
 *     summary: Delete a session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Session deleted successfully
 *       404:
 *         description: Session not found
 */
router.delete('/:sessionId', [
  param('sessionId').notEmpty()
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res:Response) => {
  const { sessionId } = req.params;
  if (sessionId) {
    await whatsAppService.deleteSession(sessionId);
  
    res.json({
      success: true,
      message: 'Session deleted successfully',
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }
}));

/**
 * @swagger
 * /api/sessions/{sessionId}/qr:
 *   get:
 *     summary: Get QR code for session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: QR code retrieved successfully
 *       404:
 *         description: Session not found or QR code not available
 */
router.get('/:sessionId/qr', [
  param('sessionId').notEmpty()
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res:Response) => {
  const { sessionId } = req.params;

  const session = await whatsAppService.getSession(sessionId);

  if (!session || !session.qrCode) {
    return res.status(404).json({
      success: false,
      error: 'QR code not available',
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }

  res.json({
    success: true,
    data: {
      qrCode: session.qrCode,
      status: session.status
    },
    timestamp: new Date().toISOString()
  } as ApiResponse);
}));

/**
 * @swagger
 * /api/sessions/{sessionId}/pairing-code:
 *   post:
 *     summary: Request pairing code for session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - phoneNumber
 *             properties:
 *               phoneNumber:
 *                 type: string
 *                 description: Phone number in international format
 *     responses:
 *       200:
 *         description: Pairing code generated successfully
 *       400:
 *         description: Invalid phone number or session not ready
 */
router.post('/:sessionId/pairing-code', [
  param('sessionId').notEmpty(),
  body('phoneNumber').isMobilePhone('any').withMessage('Invalid phone number')
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res: Response) => {
  const { sessionId } = req.params;
  const { phoneNumber } = req.body;

  try {
    if (sessionId) {
      const pairingCode = await whatsAppService.requestPairingCode(sessionId, phoneNumber);
  
      res.json({
        success: true,
        data: {
          pairingCode,
          phoneNumber,
          sessionId
        },
        message: 'Pairing code generated successfully',
        timestamp: new Date().toISOString()
      } as ApiResponse);

    }
  } catch (error: any) {
    res.status(400).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }
}));

/**
 * @swagger
 * /api/sessions/{sessionId}/status:
 *   get:
 *     summary: Get session connection status
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Session status retrieved successfully
 */
router.get('/:sessionId/status', [
  param('sessionId').notEmpty()
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res:Response) => {
  const { sessionId } = req.params;

  if (sessionId) {
    const session = await whatsAppService.getSession(sessionId);
    const dbSession = await dbService.getSession(sessionId);
  
    res.json({
      success: true,
      data: {
        sessionId,
        status: session?.status || SessionStatus.DISCONNECTED,
        phoneNumber: session?.phoneNumber || dbSession?.phoneNumber,
        name: session?.name || dbSession?.name,
        lastSeen: session?.lastSeen || dbSession?.lastSeen,
        isConnected: session?.status === SessionStatus.CONNECTED
      },
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }
}));

/**
 * @swagger
 * /api/sessions/{sessionId}/restart:
 *   post:
 *     summary: Restart a session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Session restart initiated
 */
router.post('/:sessionId/restart', [
  param('sessionId').notEmpty()
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res:Response) => {
  const { sessionId } = req.params;

  try {
    if (sessionId) {
      // Check if session exists in database
      const existingSession = await dbService.getSession(sessionId);
      
      if (existingSession) {
        // Preserve the existing workflowId and userId
        const workflowId = existingSession.workflowId || '';
        const userId = existingSession.user.id;
        
        // Fully Delete session (including auth files)
        await whatsAppService.permanentlyDeleteSession(sessionId);
        
        // Create session with the same workflowId and userId
        const session = await whatsAppService.createSession(sessionId, workflowId, userId, false);
  
        res.status(201).json({
          success: true,
          data: serializeSession(session),
          message: 'Session restarted successfully',
          timestamp: new Date().toISOString()
        } as ApiResponse);
      } else {
        res.status(404).json({
          success: false,
          message: 'Session not found',
          timestamp: new Date().toISOString()
        } as ApiResponse);
    }
  }
  } catch (error: any) {
    res.status(500).json({
      success: false,
      error: 'Failed to restart session',
      message: error.message,
      timestamp: new Date().toISOString()
    } as ApiResponse);
  }
}));

/**
 * @swagger
 * /api/sessions/{sessionId}/workflow:
 *   post:
 *     summary: Set workflow ID for a session
 *     tags: [Sessions]
 *     security:
 *       - ApiKeyAuth: []
 *     parameters:
 *       - in: path
 *         name: sessionId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - workflowId
 *             properties:
 *               workflowId:
 *                 type: string
 *                 description: Workflow ID to associate with the session
 *     responses:
 *       200:
 *         description: Workflow ID set successfully
 *       400:
 *         description: Validation error
 *       404:
 *         description: Session not found
 */
router.post('/:sessionId/workflow', [
  param('sessionId').notEmpty(),
  body('workflowId').notEmpty().trim().isLength({ min: 1, max: 100 })
], sessionMiddleware, handleValidationErrors, asyncHandler(async (req:AuthenticatedRequest, res:Response) => {
  const { sessionId } = req.params;
  const { workflowId } = req.body;

  if (sessionId) {
    // Check if session exists
    const existingSession = await dbService.getSession(sessionId);
    if (!existingSession) {
      return res.status(404).json({
        success: false,
        error: 'Session not found',
        timestamp: new Date().toISOString()
      } as ApiResponse);
    }
  
    // Update session with workflow ID
    await dbService.updateSession(sessionId, { workflowId: workflowId });
  
    res.json({
      success: true,
      data: {
        sessionId,
        workflowId
      },
      message: 'Workflow ID set successfully',
      timestamp: new Date().toISOString()
    } as ApiResponse);

  }
}));

export default router;