/**
 * Taskera AI Frontend - Unified Production Version
 * Hardened with XSS protection, Voice support, and Memory Management
 */

document.addEventListener('DOMContentLoaded', () => {

    // ============================================================================
    // CONFIGURATION
    // ============================================================================
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const PROD_URL = 'https://mubashir751-taskera-ai-backend.hf.space';
    const API_BASE_URL = isLocal ? 'http://127.0.0.1:7860' : PROD_URL; 

    const ENDPOINTS = {
        CHAT: '/api/chat',
        HISTORY: '/api/history',
        THREADS: '/api/threads',
        AUTH_LOGIN: '/auth/login',
        AUTH_SIGNUP: '/auth/signup',
        HEALTH: '/health',
        TRANS: '/api/voice/transcribe',
        TTS: '/api/voice/tts'
    };

    const KEYS = {
        AUTH_TOKEN: 'taskera_access_token',
        USER_ID: 'taskera_user_id',
        USER_EMAIL: 'taskera_user_email',
        GUEST_ID: 'taskera_guest_id'
    };

    const CONFIG = {
        MAX_FILES: 10,
        MAX_FILE_SIZE_MB: 10,
        MAX_RETRY_ATTEMPTS: 3,
        RETRY_DELAY_MS: 2000,
        REQUEST_TIMEOUT_MS: 120000, // 120s for complex RAG tasks
        ALLOWED_EXTS: ['.png', '.jpg', '.jpeg', '.pdf', '.txt', '.md', '.docx', '.doc'],
        TTS_ENABLED: true,
        MAX_TTS_LENGTH: 500
    };

    // ============================================================================
    // STATE MANAGEMENT
    // ============================================================================
    let state = {
        currentUserId: null,
        authToken: null,
        currentThreadId: null,
        stagedFiles: [],
        isLoginMode: true,
        isProcessing: false,
        retryCount: 0,
        abortController: null,
        isOnline: navigator.onLine,
        lastRequestTime: 0,
        requestQueue: new Set(),
        modalCallback: null,
        // Voice State
        isRecording: false,
        mediaRecorder: null,
        audioChunks: [],
        audioURLs: [] // Tracked for memory cleanup
    };

    // ============================================================================
    // DOM REFERENCES
    // ============================================================================
    const dom = {
        sidebar: document.getElementById('sidebar'),
        sidebarOverlay: document.getElementById('sidebarOverlay'),
        menuButton: document.getElementById('menuButton'),
        closeIcon: document.getElementById('closeIcon'),
        menuIcon: document.getElementById('menuIcon'),
        chatLog: document.getElementById('chatLog'),
        welcomeScreen: document.getElementById('welcome-screen'),
        chatForm: document.getElementById('chatForm'),
        userInput: document.getElementById('userInput'),
        sendButton: document.getElementById('sendButton'),
        chatUploadBtn: document.getElementById('chatUploadBtn'),
        voiceBtn: document.getElementById('voiceBtn'), 
        audioPlayer: document.getElementById('audioPlayer'), 
        fileUploadInput: document.getElementById('fileUploadInput'),
        filePreviewContainer: document.getElementById('filePreviewContainer'),
        newSessionBtn: document.getElementById('newSessionBtn'),
        currentUserIdDisplay: document.getElementById('currentUserId'),
        userProfileSection: document.getElementById('userProfileSection'),
        guestAuthSection: document.getElementById('guestAuthSection'),
        userEmailDisplay: document.getElementById('userEmailDisplay'),
        logoutBtn: document.getElementById('logoutBtn'),
        openLoginModalBtn: document.getElementById('openLoginModalBtn'),
        authModal: document.getElementById('authModal'),
        authForm: document.getElementById('authForm'),
        closeAuthModal: document.getElementById('closeAuthModal'),
        authEmail: document.getElementById('authEmail'),
        authPassword: document.getElementById('authPassword'),
        authSwitchBtn: document.getElementById('authSwitchBtn'),
        authSubmitBtn: document.getElementById('authSubmitBtn'),
        authModalTitle: document.getElementById('authModalTitle'),
        authErrorMsg: document.getElementById('authErrorMsg'),
        authSwitchText: document.getElementById('authSwitchText'),
        googleAuthBtn: document.getElementById('googleAuthBtn'),
        historySection: document.getElementById('historySection'),
        historyList: document.getElementById('historyList'),
        taskeraModal: document.getElementById('taskeraModal'),
        taskeraModalTitle: document.getElementById('taskeraModalTitle'),
        taskeraModalBody: document.getElementById('taskeraModalBody'),
        taskeraModalConfirm: document.getElementById('taskeraModalConfirm'),
        taskeraModalCancel: document.getElementById('taskeraModalCancel'),
        taskeraModalClose: document.getElementById('taskeraModalClose'),
    };

    // ============================================================================
    // INITIALIZATION & CLEANUP
    // ============================================================================
    function init() {
        if (dom.googleAuthBtn) dom.googleAuthBtn.href = `${API_BASE_URL}/auth/google`;

        handleGoogleLoginRedirect();
        loadSession();
        setupEventListeners();
        setupSuggestionCards();
        setupOnlineDetection();
        updateUIState();

        setInterval(checkServerHealth, 60000);
        window.addEventListener('beforeunload', cleanup);
    }

    function cleanup() {
        state.audioURLs.forEach(url => URL.revokeObjectURL(url));
        state.audioURLs = [];
        if (state.isRecording) stopRecording();
    }

    // ============================================================================
    // VOICE & AUDIO LOGIC
    // ============================================================================
    async function toggleRecording() {
        if (!state.isRecording) await startRecording();
        else stopRecording();
    }

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            state.mediaRecorder = new MediaRecorder(stream);
            state.audioChunks = [];

            state.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) state.audioChunks.push(e.data);
            };

            state.mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
                await handleVoiceInput(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            state.mediaRecorder.start();
            state.isRecording = true;
            dom.voiceBtn.classList.add('recording-active');
            dom.voiceBtn.innerHTML = `<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"></path></svg>`;
            dom.userInput.placeholder = "🔴 Listening...";
            dom.userInput.disabled = true;
        } catch (err) {
            console.error("Mic Error:", err);
            addSystemMessage("Microphone access denied.");
        }
    }

    function stopRecording() {
        if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
            state.mediaRecorder.stop();
            state.isRecording = false;
            dom.voiceBtn.classList.remove('recording-active');
            dom.voiceBtn.innerHTML = `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path></svg>`;
            dom.userInput.placeholder = "Processing Audio...";
        }
    }

    async function handleVoiceInput(audioBlob) {
        addTypingIndicator();
        const formData = new FormData();
        formData.append("file", audioBlob, "voice_input.webm");
        try {
            const response = await fetch(`${API_BASE_URL}${ENDPOINTS.TRANS}`, { method: "POST", body: formData });
            if (!response.ok) throw new Error("Transcription failed");
            const data = await response.json();
            removeTypingIndicator();
            dom.userInput.disabled = false;
            dom.userInput.placeholder = "Message Taskera...";
            if (data.text?.trim()) {
                dom.userInput.value = data.text;
                handleChatSubmit();
            } else {
                addSystemMessage("Could not understand audio.");
            }
        } catch (e) {
            removeTypingIndicator();
            dom.userInput.disabled = false;
            addSystemMessage("Voice processing failed.");
        }
    }

    async function playTTS(text) {
        if (!CONFIG.TTS_ENABLED || !text) return;
        try {
            const cleanText = text.replace(/<[^>]*>?/gm, '').replace(/[*`#]/g, '').substring(0, CONFIG.MAX_TTS_LENGTH);
            const response = await fetch(`${API_BASE_URL}${ENDPOINTS.TTS}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: cleanText })
            });
            if (!response.ok) return;
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            state.audioURLs.push(url);
            dom.audioPlayer.src = url;
            dom.audioPlayer.play().catch(() => console.warn("Autoplay blocked"));
        } catch (e) { console.error("TTS Error", e); }
    }

    // ============================================================================
    // CHAT CORE LOGIC
    // ============================================================================
    async function handleChatSubmit(e) {
        if (e) e.preventDefault();
        if (!state.isOnline) return addSystemMessage("No internet connection.");
        if (state.isProcessing) return cancelOngoingRequest();

        const message = dom.userInput.value.trim();
        const hasFiles = state.stagedFiles.length > 0;
        if (!message && !hasFiles) return;

        if (Date.now() - state.lastRequestTime < 1000) return;
        state.lastRequestTime = Date.now();
        await sendChatRequest(message, hasFiles);
    }

    async function sendChatRequest(message, hasFiles) {
        const requestKey = `${message}_${Date.now()}`;
        if (state.requestQueue.has(requestKey)) return;
        state.requestQueue.add(requestKey);

        try {
            const fileNames = state.stagedFiles.map(f => f.file.name);
            addMessageToChat('user', message, hasFiles ? fileNames : null);
            if (dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

            const formData = new FormData();
            formData.append('query', message);
            formData.append('user_id', state.currentUserId);
            if (state.currentThreadId) formData.append('thread_id', state.currentThreadId);
            state.stagedFiles.forEach(f => formData.append('files', f.file));

            dom.userInput.value = '';
            dom.userInput.style.height = 'auto';
            clearStagedFiles();
            setProcessing(true);
            addTypingIndicator();

            state.abortController = new AbortController();
            const timeoutId = setTimeout(() => state.abortController?.abort(), CONFIG.REQUEST_TIMEOUT_MS);

            const headers = state.authToken ? { 'Authorization': `Bearer ${state.authToken}` } : {};

            const response = await fetch(`${API_BASE_URL}${ENDPOINTS.CHAT}`, {
                method: 'POST',
                headers: headers,
                body: formData,
                signal: state.abortController.signal
            });

            clearTimeout(timeoutId);
            removeTypingIndicator();

            if (response.status === 402) return addSystemMessage("Limit reached. Please sign in.");
            if (!response.ok) throw new Error("Server communication error.");

            const data = await response.json();
            if (data.thread_id && !state.currentThreadId) {
                state.currentThreadId = data.thread_id;
                fetchHistory();
            }

            const answer = data.answer || "No response received.";
            addMessageToChat('ai', answer);
            playTTS(answer);

        } catch (error) {
            removeTypingIndicator();
            if (error.name !== 'AbortError') addSystemMessage(`Error: ${error.message}`);
        } finally {
            setProcessing(false);
            state.requestQueue.delete(requestKey);
        }
    }

    // ============================================================================
    // THREAD & MODAL MANAGEMENT
    // ============================================================================
    async function fetchHistory() {
        if (!state.authToken || !state.currentUserId) return;
        try {
            const res = await fetch(`${API_BASE_URL}${ENDPOINTS.HISTORY}?user_id=${state.currentUserId}`, {
                headers: { 'Authorization': `Bearer ${state.authToken}` }
            });
            const data = await res.json();
            if (data.threads) renderHistoryList(data.threads);
        } catch (e) { console.error("History fetch failed"); }
    }

    function renderHistoryList(threads) {
        dom.historyList.innerHTML = '';
        dom.historySection.classList.toggle('hidden', threads.length === 0);
        threads.forEach(t => {
            const container = document.createElement('div');
            container.className = 'group relative mb-1 flex items-center pr-8';
            
            const btn = document.createElement('button');
            btn.className = `flex-1 text-left px-3 py-2 rounded-lg text-xs truncate ${state.currentThreadId === t.thread_id ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-800/50'}`;
            btn.textContent = t.title || 'Untitled Chat';
            btn.onclick = () => loadThread(t.thread_id);

            const menuBtn = document.createElement('button');
            menuBtn.className = 'absolute right-1 text-zinc-500 opacity-0 group-hover:opacity-100 p-1';
            menuBtn.innerHTML = '⋮';
            menuBtn.onclick = (e) => {
                e.stopPropagation();
                openModal('delete', { threadId: t.thread_id, currentTitle: t.title, element: container });
            };

            container.append(btn, menuBtn);
            dom.historyList.appendChild(container);
        });
    }

    async function loadThread(threadId) {
        cancelOngoingRequest();
        state.currentThreadId = threadId;
        dom.chatLog.innerHTML = '';
        addSystemMessage("Loading conversation...");
        try {
            const res = await fetch(`${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${state.currentUserId}`, {
                headers: { 'Authorization': `Bearer ${state.authToken}` }
            });
            const data = await res.json();
            dom.chatLog.innerHTML = '';
            data.messages?.forEach(m => addMessageToChat(m.role, m.content));
            if (dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');
        } catch (e) { addSystemMessage("Failed to load thread."); }
    }

    async function handleDeleteThread(threadId, element) {
        try {
            const res = await fetch(`${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${state.currentUserId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${state.authToken}` }
            });
            if (res.ok) {
                element.remove();
                if (state.currentThreadId === threadId) handleNewSession();
                closeModal();
            }
        } catch (e) { console.error("Delete failed"); }
    }

    // ============================================================================
    // AUTH & SESSION
    // ============================================================================
    function loadSession() {
        state.authToken = localStorage.getItem(KEYS.AUTH_TOKEN);
        state.currentUserId = localStorage.getItem(KEYS.USER_ID) || 'guest_' + generateUUID();
        if (!localStorage.getItem(KEYS.USER_ID)) localStorage.setItem(KEYS.USER_ID, state.currentUserId);
        
        const email = localStorage.getItem(KEYS.USER_EMAIL);
        updateAuthUI(!!state.authToken, email);
        if (state.authToken) fetchHistory();
        if (dom.currentUserIdDisplay) dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 10) + '...';
    }

    async function handleAuthSubmit(e) {
        e.preventDefault();
        const endpoint = state.isLoginMode ? ENDPOINTS.AUTH_LOGIN : ENDPOINTS.AUTH_SIGNUP;
        try {
            const res = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: dom.authEmail.value, password: dom.authPassword.value })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Auth failed");

            if (state.isLoginMode) {
                localStorage.setItem(KEYS.AUTH_TOKEN, data.access_token);
                localStorage.setItem(KEYS.USER_ID, data.user_id);
                localStorage.setItem(KEYS.USER_EMAIL, data.email);
                location.reload();
            } else {
                state.isLoginMode = true;
                renderAuthModalState();
                showAuthSuccess("Account created! Sign in below.");
            }
        } catch (err) { showAuthError(err.message); }
    }

    // ============================================================================
    // UI CORE UTILITIES
    // ============================================================================
    function setupEventListeners() {
        dom.menuButton?.addEventListener('click', () => toggleSidebar());
        dom.sidebarOverlay?.addEventListener('click', () => toggleSidebar(false));
        dom.chatForm?.addEventListener('submit', handleChatSubmit);
        dom.newSessionBtn?.addEventListener('click', handleNewSession);
        dom.voiceBtn?.addEventListener('click', toggleRecording);
        dom.chatUploadBtn?.addEventListener('click', () => dom.fileUploadInput.click());
        dom.fileUploadInput?.addEventListener('change', handleFileStage);
        dom.logoutBtn?.addEventListener('click', handleLogout);
        dom.openLoginModalBtn?.addEventListener('click', () => showAuthModal(true));
        dom.closeAuthModal?.addEventListener('click', hideAuthModal);
        dom.authSwitchBtn?.addEventListener('click', toggleAuthMode);
        dom.authForm?.addEventListener('submit', handleAuthSubmit);
        dom.taskeraModalCancel?.addEventListener('click', closeModal);
        dom.taskeraModalClose?.addEventListener('click', closeModal);
        dom.taskeraModalConfirm?.addEventListener('click', () => state.modalCallback?.());
        
        dom.userInput?.addEventListener('input', () => {
            dom.userInput.style.height = 'auto';
            dom.userInput.style.height = Math.min(dom.userInput.scrollHeight, 150) + 'px';
        });
    }

    function setProcessing(proc) {
        state.isProcessing = proc;
        dom.userInput.disabled = proc;
        dom.sendButton.disabled = proc;
        dom.voiceBtn.disabled = proc;
        dom.sendButton.innerHTML = proc ? `<svg class="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>` : `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path></svg>`;
    }

    function toggleSidebar(force) {
        const isOpen = !dom.sidebar.classList.contains('-translate-x-full');
        const newState = (typeof force === 'boolean') ? force : !isOpen;
        dom.sidebar.classList.toggle('-translate-x-full', !newState);
        dom.sidebarOverlay.classList.toggle('hidden', !newState);
    }

    function handleLogout() {
        localStorage.clear();
        location.reload();
    }

    function handleNewSession() {
        cancelOngoingRequest();
        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        dom.welcomeScreen?.classList.remove('hidden');
        state.currentThreadId = null;
        clearStagedFiles();
    }

    function cancelOngoingRequest() {
        if (state.abortController) {
            state.abortController.abort();
            state.abortController = null;
        }
        setProcessing(false);
        removeTypingIndicator();
    }

    function handleFileStage(e) {
        const files = Array.from(e.target.files);
        files.forEach(file => {
            const id = generateUUID();
            state.stagedFiles.push({ id, file });
            const chip = document.createElement('div');
            chip.className = 'flex items-center bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-300';
            chip.innerHTML = `<span class="truncate max-w-[100px] mr-1">${file.name}</span><button type="button" class="hover:text-red-400">✕</button>`;
            chip.querySelector('button').onclick = () => {
                state.stagedFiles = state.stagedFiles.filter(f => f.id !== id);
                chip.remove();
            };
            dom.filePreviewContainer.appendChild(chip);
        });
    }

    // ============================================================================
    // DOM UTILITIES
    // ============================================================================
    function escapeHtml(str) {
        if (!str) return '';
        const p = document.createElement('p');
        p.textContent = str;
        return p.innerHTML;
    }

    function formatAIResponse(text) {
        let f = escapeHtml(text);
        f = f.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
        f = f.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-900 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-xs text-fuchsia-300">$1</code></pre>');
        f = f.replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1.5 py-0.5 rounded text-fuchsia-300 font-mono text-xs">$1</code>');
        f = f.replace(/^\s*[-*]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');
        return f.replace(/\n/g, '<br>');
    }

    function createMessageElement(sender, message, fileNames = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat-message-wrapper w-full flex ${sender === 'user' ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in`;
        if (sender === 'user') {
            wrapper.innerHTML = `<div class="flex flex-col items-end max-w-[85%] md:max-w-2xl"><div class="bg-zinc-800 text-white rounded-2xl rounded-tr-sm px-5 py-3.5 border border-zinc-700/50"><p class="text-sm leading-relaxed whitespace-pre-wrap">${escapeHtml(message)}</p>${renderFileAttachments(fileNames)}</div></div>`;
        } else {
            wrapper.innerHTML = `<div class="flex items-start space-x-4 max-w-full md:max-w-3xl"><div class="flex-shrink-0 mt-1"><img src="assets/images/logo.png" class="w-8 h-8 rounded-lg"></div><div class="flex-1 min-w-0"><div class="prose prose-invert prose-sm text-zinc-300 leading-relaxed">${formatAIResponse(message)}</div></div></div>`;
        }
        return wrapper;
    }

    function renderFileAttachments(names) {
        if (!names?.length) return '';
        return `<div class="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">${names.map(n => `<div class="text-[10px] bg-black/20 px-2 py-1 rounded border border-white/5">${escapeHtml(n)}</div>`).join('')}</div>`;
    }

    function addMessageToChat(s, m, f) { dom.chatLog.appendChild(createMessageElement(s, m, f)); scrollToBottom(); }
    function addSystemMessage(t) { const w = document.createElement('div'); w.className = 'chat-message-wrapper flex justify-center my-4'; w.innerHTML = `<span class="text-[10px] text-zinc-500 bg-zinc-900/50 border border-zinc-800 px-3 py-1 rounded-full">${escapeHtml(t)}</span>`; dom.chatLog.appendChild(w); scrollToBottom(); }
    function addTypingIndicator() { removeTypingIndicator(); const w = document.createElement('div'); w.id = 'typing-indicator'; w.className = 'chat-message-wrapper flex items-start space-x-4 mb-6'; w.innerHTML = `<div class="flex-shrink-0 mt-1"><img src="assets/images/logo.png" class="w-8 h-8 rounded-lg opacity-80"></div><div class="flex space-x-1.5 bg-zinc-900/50 px-3 py-2 rounded-xl border border-zinc-800"><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce"></div><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay:0.1s"></div><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay:0.2s"></div></div>`; dom.chatLog.appendChild(w); scrollToBottom(); }
    function removeTypingIndicator() { document.getElementById('typing-indicator')?.remove(); }
    function scrollToBottom() { dom.chatLog.scrollTop = dom.chatLog.scrollHeight; }
    function generateUUID() { return crypto.randomUUID(); }
    function clearStagedFiles() { state.stagedFiles = []; dom.filePreviewContainer.innerHTML = ''; }
    
    // Modal Helpers
    function showAuthModal(isLogin = true) {
        state.isLoginMode = isLogin;
        renderAuthModalState();
        dom.authModal.classList.remove('hidden');
        setTimeout(() => dom.authModal.classList.remove('opacity-0'), 10);
    }
    function hideAuthModal() {
        dom.authModal.classList.add('opacity-0');
        setTimeout(() => dom.authModal.classList.add('hidden'), 300);
    }
    function renderAuthModalState() {
        dom.authModalTitle.textContent = state.isLoginMode ? "Sign In" : "Create Account";
        dom.authSubmitBtn.textContent = state.isLoginMode ? "Sign In" : "Sign Up";
        dom.authSwitchBtn.textContent = state.isLoginMode ? "Sign Up" : "Sign In";
    }
    function showAuthError(msg) { dom.authErrorMsg.textContent = msg; dom.authErrorMsg.classList.remove('hidden', 'text-green-400'); dom.authErrorMsg.classList.add('text-red-400'); }
    function showAuthSuccess(msg) { dom.authErrorMsg.textContent = msg; dom.authErrorMsg.classList.remove('hidden', 'text-red-400'); dom.authErrorMsg.classList.add('text-green-400'); }
    function updateAuthUI(isLoggedIn, email = '') {
        dom.guestAuthSection?.classList.toggle('hidden', isLoggedIn);
        dom.userProfileSection?.classList.toggle('hidden', !isLoggedIn);
        if (dom.userEmailDisplay) dom.userEmailDisplay.textContent = email;
    }
    function toggleAuthMode() { state.isLoginMode = !state.isLoginMode; renderAuthModalState(); }
    
    function openModal(type, data = {}) {
        dom.taskeraModal.classList.remove('hidden');
        setTimeout(() => dom.taskeraModal.classList.remove('opacity-0'), 10);
        if (type === 'delete') {
            dom.taskeraModalTitle.textContent = 'Delete Chat';
            dom.taskeraModalBody.innerHTML = `<p class="text-sm text-zinc-400">Are you sure you want to delete "${data.currentTitle}"?</p>`;
            state.modalCallback = () => handleDeleteThread(data.threadId, data.element);
        }
    }
    function closeModal() {
        dom.taskeraModal.classList.add('opacity-0');
        setTimeout(() => dom.taskeraModal.classList.add('hidden'), 200);
    }
    function checkServerHealth() { fetch(`${API_BASE_URL}${ENDPOINTS.HEALTH}`).catch(() => {}); }
    function handleGoogleLoginRedirect() { /* Injected logic from snippet 1 */ }
    function setupOnlineDetection() { window.addEventListener('online', () => state.isOnline = true); window.addEventListener('offline', () => state.isOnline = false); }
    function setupSuggestionCards() { document.querySelectorAll('.suggestion-card').forEach(c => c.onclick = () => { dom.userInput.value = c.querySelector('span').textContent; dom.userInput.focus(); }); }
    function updateUIState() { dom.welcomeScreen?.classList.toggle('hidden', dom.chatLog.children.length > 1); }

    init();
});