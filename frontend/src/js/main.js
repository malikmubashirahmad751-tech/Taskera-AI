document.addEventListener('DOMContentLoaded', () => {
    
    
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    
    const PROD_URL = 'https://mubashir751-taskera-ai-backend.hf.space';
    
    const API_BASE_URL = isLocal 
        ? 'http://127.0.0.1:7860' 
        : PROD_URL;
        
    const ENDPOINTS = {
        CHAT: '/api/chat',
        HISTORY: '/api/history',
        THREADS: '/api/threads',
        AUTH_LOGIN: '/auth/login',
        AUTH_SIGNUP: '/auth/signup',
        HEALTH: '/health'
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
        REQUEST_TIMEOUT_MS: 60000, 
        ALLOWED_EXTS: ['.png', '.jpg', '.jpeg', '.pdf', '.txt', '.md', '.docx', '.doc']
    };


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
        requestQueue: new Set() 
    };

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
    };


    function init() {
        console.log(`Connecting to: ${API_BASE_URL}`);
        
        if (dom.googleAuthBtn) {
            dom.googleAuthBtn.href = `${API_BASE_URL}/auth/google`; 
        }
        
        
        handleGoogleLoginRedirect();
        loadSession();
        setupEventListeners();
        setupSuggestionCards();
        setupOnlineDetection();
        updateUIState();
        
        setInterval(checkServerHealth, 60000); 
    }


    function setupOnlineDetection() {
        window.addEventListener('online', () => {
            state.isOnline = true;
            addSystemMessage("Connection restored");
        });
        
        window.addEventListener('offline', () => {
            state.isOnline = false;
            addSystemMessage("You're offline. Messages will fail until reconnected.");
        });
    }

    async function checkServerHealth() {
        if (!state.isOnline) return;
        try {
            const response = await fetch(`${API_BASE_URL}${ENDPOINTS.HEALTH}`, {
                method: 'GET',
                signal: AbortSignal.timeout(5000)
            });
            if (!response.ok) console.warn("⚠ Server health check failed");
        } catch (e) {
            console.warn("⚠ Server unreachable:", e.message);
        }
    }


    async function fetchHistory() {
        if (!state.authToken || !dom.historyList || !state.currentUserId) return;

        try {
            const url = `${API_BASE_URL}${ENDPOINTS.HISTORY}?user_id=${encodeURIComponent(state.currentUserId)}`;
            
            const response = await fetch(url, {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${state.authToken}` },
                signal: AbortSignal.timeout(10000)
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            if (data.success && data.threads && data.threads.length > 0) {
                renderHistoryList(data.threads);
                dom.historySection.classList.remove('hidden');
            } else {
                dom.historySection.classList.add('hidden');
            }
        } catch (e) {
            console.error("Failed to fetch history:", e);
        }
    }

    function renderHistoryList(threads) {
        const fragment = document.createDocumentFragment();
        
        threads.forEach(thread => {
            const btnContainer = document.createElement('div');
            btnContainer.className = 'group relative mb-1';

            const btn = document.createElement('button');
            const isActive = state.currentThreadId === thread.thread_id;
            
            btn.className = `w-full text-left px-3 py-2 rounded-lg text-xs transition-colors truncate flex flex-col 
                ${isActive ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-white'}`;
            
            const date = new Date(thread.updated_at || thread.created_at)
                .toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            
            btn.innerHTML = `
                <span class="block font-medium truncate w-[90%]">${escapeHtml(thread.title || 'Conversation')}</span>
                <span class="text-[10px] opacity-50">${date}</span>
            `;
            
            btn.onclick = () => loadThread(thread.thread_id);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'absolute right-1 top-2 text-zinc-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity p-1';
            deleteBtn.innerHTML = '×';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                deleteThread(thread.thread_id, btnContainer);
            };

            btnContainer.appendChild(btn);
            btnContainer.appendChild(deleteBtn);
            fragment.appendChild(btnContainer);
        });
        
        dom.historyList.innerHTML = '';
        dom.historyList.appendChild(fragment);
    }

    async function deleteThread(threadId, element) {
        if (!confirm("Delete this conversation?")) return;
        
        try {
            const url = `${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${encodeURIComponent(state.currentUserId)}`;
            
            const response = await fetch(url, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${state.authToken}` },
                signal: AbortSignal.timeout(10000)
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            element.remove();
            if (state.currentThreadId === threadId) handleNewSession();
            addSystemMessage("Conversation deleted");
            
        } catch (e) {
            console.error("Delete failed", e);
            addSystemMessage("Failed to delete conversation");
        }
    }

    async function loadThread(threadId) {
        if (state.currentThreadId === threadId) return;
        
        cancelOngoingRequest();
        state.currentThreadId = threadId;
        
        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        if(dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');
        addSystemMessage("Loading conversation...");
        
        fetchHistory(); 
        if (window.innerWidth < 768) toggleSidebar(false);

        try {
            const url = `${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${encodeURIComponent(state.currentUserId)}`;
            
            const response = await fetch(url, {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${state.authToken}` },
                signal: AbortSignal.timeout(15000)
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            dom.chatLog.innerHTML = ''; 

            if (data.success && data.messages && data.messages.length > 0) {
                const fragment = document.createDocumentFragment();
                data.messages.forEach(msg => {
                    const wrapper = createMessageElement(msg.role, msg.content);
                    fragment.appendChild(wrapper);
                });
                dom.chatLog.appendChild(fragment);
                scrollToBottom();
            } else {
                addSystemMessage("No messages found for this thread.");
            }
        } catch (e) {
            console.error("Failed to load thread:", e);
            addSystemMessage("Error loading conversation history.");
        }
    }


    function handleGoogleLoginRedirect() {
        const urlParams = new URLSearchParams(window.location.search);
        
        if (urlParams.get('google_auth') === 'success') {
            const token = urlParams.get('access_token');
            const email = urlParams.get('email');
            const userId = urlParams.get('user_id');

            if (token && email && userId) {
                localStorage.setItem(KEYS.AUTH_TOKEN, token);
                localStorage.setItem(KEYS.USER_ID, userId);
                localStorage.setItem(KEYS.USER_EMAIL, email);
                
                state.authToken = token;
                state.currentUserId = userId;
                
                window.history.replaceState({}, document.title, window.location.pathname);
                addSystemMessage("Successfully logged in with Google!");
                updateAuthUI(true, email);
                fetchHistory();
            }
        } else if (urlParams.get('error') === 'auth_failed') {
            addSystemMessage("Authentication failed: " + (urlParams.get('details') || 'Unknown error'));
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }

    function loadSession() {
        const storedToken = localStorage.getItem(KEYS.AUTH_TOKEN);
        const storedUserId = localStorage.getItem(KEYS.USER_ID);
        const storedEmail = localStorage.getItem(KEYS.USER_EMAIL);

        if (storedToken && storedUserId) {
            state.authToken = storedToken;
            state.currentUserId = storedUserId;
            updateAuthUI(true, storedEmail);
            fetchHistory();
        } else {
            let guestId = localStorage.getItem(KEYS.GUEST_ID);
            if (!guestId) {
                guestId = 'guest_' + generateUUID();
                localStorage.setItem(KEYS.GUEST_ID, guestId);
            }
            state.currentUserId = guestId;
            updateAuthUI(false);
            if(dom.historySection) dom.historySection.classList.add('hidden');
        }
        
        if (dom.currentUserIdDisplay) {
            dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 10) + '...';
        }
    }

    function setupEventListeners() {
        if(dom.menuButton) dom.menuButton.addEventListener('click', () => toggleSidebar());
        if(dom.sidebarOverlay) dom.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));
        
        if(dom.chatForm) dom.chatForm.addEventListener('submit', handleChatSubmit);
        if(dom.userInput) {
            dom.userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!state.isProcessing) handleChatSubmit(e);
                }
            });
            dom.userInput.addEventListener('input', () => {
                dom.userInput.style.height = 'auto';
                dom.userInput.style.height = Math.min(dom.userInput.scrollHeight, 150) + 'px';
            });
        }
        
        if(dom.chatUploadBtn) dom.chatUploadBtn.addEventListener('click', () => {
            if (!state.isProcessing) dom.fileUploadInput.click();
        });
        if(dom.fileUploadInput) dom.fileUploadInput.addEventListener('change', handleFileStage);
        
        if(dom.filePreviewContainer) {
            dom.filePreviewContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('button[data-file-id]');
                if (btn) handleFileRemove(btn.dataset.fileId);
            });
        }
        
        if(dom.newSessionBtn) dom.newSessionBtn.addEventListener('click', handleNewSession);
        if(dom.openLoginModalBtn) dom.openLoginModalBtn.addEventListener('click', () => showAuthModal(true));
        if(dom.closeAuthModal) dom.closeAuthModal.addEventListener('click', hideAuthModal);
        if(dom.authSwitchBtn) dom.authSwitchBtn.addEventListener('click', toggleAuthMode);
        if(dom.authForm) dom.authForm.addEventListener('submit', handleAuthSubmit);
        if(dom.logoutBtn) dom.logoutBtn.addEventListener('click', handleLogout);
        if(dom.authModal) {
            dom.authModal.addEventListener('click', (e) => { 
                if (e.target === dom.authModal) hideAuthModal(); 
            });
        }
        
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && state.authToken) {
                fetchHistory(); 
            }
        });
    }

    function setupSuggestionCards() {
        document.querySelectorAll('.suggestion-card').forEach(card => {
            card.addEventListener('click', () => {
                if (state.isProcessing) return;
                const textSpan = card.querySelector('span.text-zinc-200') || card.querySelector('h3') || card.querySelector('p');
                if (textSpan) {
                    dom.userInput.value = textSpan.textContent.trim();
                    dom.userInput.focus();
                }
            });
        });
    }

    async function handleChatSubmit(e) {
        if(e) e.preventDefault();
        
        if (!state.isOnline) {
            addSystemMessage("No internet connection.");
            return;
        }
        
        if (state.isProcessing) {
            cancelOngoingRequest();
            return;
        }
        
        const message = dom.userInput.value.trim();
        const hasFiles = state.stagedFiles.length > 0;
        
        if (!message && !hasFiles) return;
        
        const now = Date.now();
        if (now - state.lastRequestTime < 1000) { 
            addSystemMessage("Please wait a moment before sending another message");
            return;
        }
        
        state.lastRequestTime = now;
        state.retryCount = 0;
        await sendChatRequest(message, hasFiles);
    }

    function cancelOngoingRequest() {
        if (state.abortController) {
            state.abortController.abort();
            state.abortController = null;
            removeTypingIndicator();
            addSystemMessage("Request cancelled");
            setProcessing(false);
        }
    }

    async function sendChatRequest(message, hasFiles) {
        const requestKey = `${message}_${state.stagedFiles.length}_${Date.now()}`;
        if (state.requestQueue.has(requestKey)) return;
        state.requestQueue.add(requestKey);
        
        try {
            const fileNames = state.stagedFiles.map(f => f.file.name);
            addMessageToChat('user', message, hasFiles ? fileNames : null);
            
            if(dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

            const formData = new FormData();
            formData.append('query', message);
            formData.append('user_id', state.currentUserId);
            
            if (state.currentThreadId) {
                formData.append('thread_id', state.currentThreadId);
            }
            
            const userEmail = localStorage.getItem(KEYS.USER_EMAIL);
            if (userEmail) formData.append('email', userEmail);
            
            state.stagedFiles.forEach(f => formData.append('files', f.file));

            dom.userInput.value = '';
            dom.userInput.style.height = 'auto';
            clearStagedFiles();
            setProcessing(true);
            addTypingIndicator();

            state.abortController = new AbortController();
            
            const timeoutId = setTimeout(() => {
                if (state.abortController) state.abortController.abort();
            }, CONFIG.REQUEST_TIMEOUT_MS);

            try {
                const headers = {};
                if (state.authToken) headers['Authorization'] = `Bearer ${state.authToken}`;

                const response = await fetch(`${API_BASE_URL}${ENDPOINTS.CHAT}`, {
                    method: 'POST',
                    headers: headers,
                    body: formData,
                    signal: state.abortController.signal
                });

                clearTimeout(timeoutId);
                removeTypingIndicator();
                state.abortController = null;

                if (response.status === 402) {
                    addSystemMessage("Free trial limit reached. Please sign in.");
                    showAuthModal(false, "Quota Exceeded");
                    return;
                }
                
                if (response.status === 401) {
                    handleLogout();
                    showAuthModal(true, "Session expired. Log in again.");
                    return;
                }

                if (response.status === 429) {
                    addSystemMessage("Rate limit exceeded. Waiting 3s...");
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    return;
                }

                if (response.status === 504 || response.status === 503) {
                    if (state.retryCount < CONFIG.MAX_RETRY_ATTEMPTS) {
                        state.retryCount++;
                        addSystemMessage(`Timeout/Busy. Retrying (${state.retryCount}/${CONFIG.MAX_RETRY_ATTEMPTS})...`);
                        await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY_MS * state.retryCount));
                        return await sendChatRequest(message, hasFiles);
                    } else {
                        addSystemMessage("Service unavailable. Please try again later.");
                        state.retryCount = 0;
                        return;
                    }
                }

                const data = await response.json();
                
                if (!response.ok) {
                    const errorMsg = data.detail?.message || data.detail || data.error || `Error: ${response.status}`;
                    throw new Error(errorMsg);
                }

                if (data.thread_id) {
                    const isNewThread = !state.currentThreadId;
                    state.currentThreadId = data.thread_id;
                    if (isNewThread && state.authToken) {
                        setTimeout(() => fetchHistory(), 1500);
                    }
                }

                let aiResponse = data.answer || JSON.stringify(data, null, 2);
                if (Array.isArray(aiResponse)) aiResponse = aiResponse.join('\n');
                
                addMessageToChat('ai', aiResponse);
                state.retryCount = 0;

            } catch (error) {
                clearTimeout(timeoutId);
                removeTypingIndicator();
                state.abortController = null;
                
                if (error.name === 'AbortError') {
                    console.log('Request cancelled/timed out');
                    addSystemMessage("Request timed out");
                    return;
                }
                
                console.error('Chat error:', error);
                
                if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                    if (state.retryCount < CONFIG.MAX_RETRY_ATTEMPTS) {
                        state.retryCount++;
                        addSystemMessage(`Connection lost. Retrying (${state.retryCount}/${CONFIG.MAX_RETRY_ATTEMPTS})...`);
                        await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY_MS * state.retryCount));
                        return await sendChatRequest(message, hasFiles);
                    } else {
                        addSystemMessage("Connection failure. Check internet.");
                        state.retryCount = 0;
                    }
                } else {
                    addSystemMessage(`Error: ${error.message}`);
                }
            }
        } finally {
            setProcessing(false);
            state.requestQueue.delete(requestKey);
        }
    }


    async function handleAuthSubmit(e) {
        e.preventDefault();
        
        const email = dom.authEmail.value.trim();
        const password = dom.authPassword.value;
        
        if (!email || !password) {
            showAuthError("Please fill in all fields");
            return;
        }
        
        dom.authSubmitBtn.disabled = true;
        dom.authSubmitBtn.textContent = "Processing...";
        dom.authErrorMsg.classList.add('hidden');

        const endpoint = state.isLoginMode ? ENDPOINTS.AUTH_LOGIN : ENDPOINTS.AUTH_SIGNUP;
        const payload = { email, password };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: AbortSignal.timeout(15000)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || data.message || "Authentication failed");
            }

            if (state.isLoginMode) {
                state.authToken = data.access_token;
                state.currentUserId = data.user_id;
                
                localStorage.setItem(KEYS.AUTH_TOKEN, state.authToken);
                localStorage.setItem(KEYS.USER_ID, state.currentUserId);
                localStorage.setItem(KEYS.USER_EMAIL, data.email);
                
                updateAuthUI(true, data.email);
                hideAuthModal();
                fetchHistory();
                addSystemMessage("Successfully logged in!");
            } else {
                state.isLoginMode = true;
                renderAuthModalState();
                showAuthSuccess("Account created! Please sign in.");
            }
        } catch (error) {
            console.error("Auth error:", error);
            showAuthError(error.message);
        } finally {
            dom.authSubmitBtn.disabled = false;
            dom.authSubmitBtn.textContent = state.isLoginMode ? "Sign In" : "Sign Up";
        }
    }

    function showAuthError(message) {
        dom.authErrorMsg.textContent = message;
        dom.authErrorMsg.classList.remove('hidden', 'text-green-400', 'bg-green-900/10');
        dom.authErrorMsg.classList.add('text-red-400', 'bg-red-900/10');
        dom.authErrorMsg.classList.remove('hidden');
    }

    function showAuthSuccess(message) {
        dom.authErrorMsg.textContent = message;
        dom.authErrorMsg.classList.remove('hidden', 'text-red-400', 'bg-red-900/10');
        dom.authErrorMsg.classList.add('text-green-400', 'bg-green-900/10');
        dom.authErrorMsg.classList.remove('hidden');
    }

    function handleLogout() {
        cancelOngoingRequest();
        
        localStorage.removeItem(KEYS.AUTH_TOKEN);
        localStorage.removeItem(KEYS.USER_ID);
        localStorage.removeItem(KEYS.USER_EMAIL);
        
        state.authToken = null;
        let guestId = 'guest_' + generateUUID();
        localStorage.setItem(KEYS.GUEST_ID, guestId);
        state.currentUserId = guestId;
        
        updateAuthUI(false);
        handleNewSession();
        if(dom.historySection) dom.historySection.classList.add('hidden');
        addSystemMessage("Logged out successfully");
    }


    function createMessageElement(sender, message, fileNames = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat-message-wrapper w-full flex ${sender === 'user' ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in`;
        
        if (sender === 'user') {
            wrapper.innerHTML = `
                <div class="flex flex-col items-end max-w-[85%] md:max-w-2xl">
                    <div class="bg-zinc-800 text-white rounded-2xl rounded-tr-sm px-5 py-3.5 shadow-md border border-zinc-700/50">
                        <p class="text-sm leading-relaxed whitespace-pre-wrap">${escapeHtml(message)}</p>
                        ${renderFileAttachments(fileNames)}
                    </div>
                </div>`;
        } else {
            wrapper.innerHTML = `
                <div class="flex items-start space-x-4 max-w-full md:max-w-3xl">
                    <div class="flex-shrink-0 mt-1">
                        <img src="assets/images/logo.png" alt="Taskera" class="w-8 h-8 rounded-lg shadow-sm">
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="prose prose-invert prose-sm max-w-none text-zinc-300 leading-relaxed">
                            ${formatAIResponse(message)}
                        </div>
                    </div>
                </div>`;
        }
        return wrapper;
    }

    function addMessageToChat(sender, message, fileNames = null) {
        const wrapper = createMessageElement(sender, message, fileNames);
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function addSystemMessage(text) {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message-wrapper flex justify-center my-4 animate-fade-in';
        wrapper.innerHTML = `<span class="text-xs text-zinc-500 bg-zinc-900/50 border border-zinc-800 px-3 py-1 rounded-full">${escapeHtml(text)}</span>`;
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function addTypingIndicator() {
        removeTypingIndicator();
        const wrapper = document.createElement('div');
        wrapper.id = 'typing-indicator';
        wrapper.className = 'chat-message-wrapper flex items-start space-x-4 mb-6 animate-fade-in';
        wrapper.innerHTML = `
            <div class="flex-shrink-0 mt-1">
                <img src="assets/images/logo.png" class="w-8 h-8 rounded-lg shadow-sm opacity-80">
            </div>
            <div class="flex items-center h-8">
                <div class="flex space-x-1.5 bg-zinc-900/50 px-3 py-2 rounded-xl border border-zinc-800">
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0s"></div>
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                    <div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                </div>
            </div>`;
        dom.chatLog.appendChild(wrapper);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            dom.chatLog.scrollTop = dom.chatLog.scrollHeight;
        });
    }

    function updateAuthUI(isLoggedIn, email = '') {
        if (isLoggedIn) {
            if(dom.guestAuthSection) dom.guestAuthSection.classList.add('hidden');
            if(dom.userProfileSection) dom.userProfileSection.classList.remove('hidden');
            if(dom.userEmailDisplay) dom.userEmailDisplay.textContent = email;
        } else {
            if(dom.guestAuthSection) dom.guestAuthSection.classList.remove('hidden');
            if(dom.userProfileSection) dom.userProfileSection.classList.add('hidden');
        }
    }

    function showAuthModal(isLogin = true, message = null) {
        state.isLoginMode = isLogin;
        renderAuthModalState();
        dom.authModal.classList.remove('hidden');
        setTimeout(() => {
            dom.authModal.classList.remove('opacity-0');
            const content = dom.authModal.querySelector('.modal-content');
            if(content) content.classList.remove('scale-95', 'opacity-0');
        }, 10);
        
        if (message) showAuthError(message);
    }

    function hideAuthModal() {
        dom.authModal.classList.add('opacity-0');
        const content = dom.authModal.querySelector('.modal-content');
        if(content) content.classList.add('scale-95', 'opacity-0');
        
        setTimeout(() => {
            dom.authModal.classList.add('hidden');
            dom.authErrorMsg.classList.add('hidden');
        }, 300);
    }

    function renderAuthModalState() {
        if (state.isLoginMode) {
            dom.authModalTitle.textContent = "Sign In";
            dom.authSubmitBtn.textContent = "Sign In";
            dom.authSwitchText.textContent = "Don't have an account?";
            dom.authSwitchBtn.textContent = "Sign Up";
        } else {
            dom.authModalTitle.textContent = "Create Account";
            dom.authSubmitBtn.textContent = "Sign Up";
            dom.authSwitchText.textContent = "Already have an account?";
            dom.authSwitchBtn.textContent = "Sign In";
        }
        dom.authErrorMsg.classList.add('hidden');
    }

    function toggleAuthMode(e) {
        e.preventDefault();
        state.isLoginMode = !state.isLoginMode;
        renderAuthModalState();
    }

    function toggleSidebar(forceState) {
        if(!dom.sidebar) return;
        const isOpen = !dom.sidebar.classList.contains('-translate-x-full');
        const newState = (typeof forceState === 'boolean') ? forceState : !isOpen;
        if (newState) {
            dom.sidebar.classList.remove('-translate-x-full');
            dom.sidebarOverlay.classList.remove('hidden');
            if(dom.menuIcon) dom.menuIcon.classList.add('hidden');
            if(dom.closeIcon) dom.closeIcon.classList.remove('hidden');
        } else {
            dom.sidebar.classList.add('-translate-x-full');
            dom.sidebarOverlay.classList.add('hidden');
            if(dom.menuIcon) dom.menuIcon.classList.remove('hidden');
            if(dom.closeIcon) dom.closeIcon.classList.add('hidden');
        }
    }

    function handleNewSession() {
        cancelOngoingRequest();
        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        if(dom.welcomeScreen) dom.welcomeScreen.classList.remove('hidden');
        clearStagedFiles();
        dom.userInput.value = '';
        dom.userInput.focus();
        toggleSidebar(false);
        state.retryCount = 0;
        state.currentThreadId = null;
        if (state.authToken) fetchHistory();
    }

    function setProcessing(isProcessing) {
        state.isProcessing = isProcessing;
        dom.userInput.disabled = isProcessing;
        dom.sendButton.disabled = isProcessing;
        dom.chatUploadBtn.disabled = isProcessing;
        
        if (isProcessing) {
            dom.sendButton.innerHTML = `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;
        } else {
            dom.sendButton.innerHTML = `<svg class="w-5 h-5 transform rotate-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path></svg>`;
            dom.userInput.focus();
        }
    }

    function updateUIState() {
        const hasMessages = dom.chatLog.querySelectorAll('.chat-message-wrapper').length > 0;
        if(dom.welcomeScreen) {
            hasMessages ? dom.welcomeScreen.classList.add('hidden') : dom.welcomeScreen.classList.remove('hidden');
        }
    }

    function formatAIResponse(text) {
        if (!text) return '';
        let formatted = escapeHtml(text);
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-900 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-xs text-fuchsia-300">$1</code></pre>');
        formatted = formatted.replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1.5 py-0.5 rounded text-fuchsia-300 font-mono text-xs">$1</code>');
        formatted = formatted.replace(/^\s*[-*]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');
        formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-fuchsia-400 hover:text-fuchsia-300 underline">$1</a>');
        return formatted.replace(/\n/g, '<br>');
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function renderFileAttachments(names) {
        if (!names || !names.length) return '';
        return `<div class="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">${names.map(name => `<div class="flex items-center text-xs text-white/70 bg-black/20 px-2 py-1 rounded border border-white/5">${escapeHtml(name)}</div>`).join('')}</div>`;
    }

    function handleFileStage(e) {
        const files = Array.from(e.target.files);
        if (state.stagedFiles.length + files.length > CONFIG.MAX_FILES) {
            addSystemMessage(`Maximum ${CONFIG.MAX_FILES} files allowed`);
            return;
        }
        
        files.forEach(file => {
            if (file.size / (1024 * 1024) > CONFIG.MAX_FILE_SIZE_MB) {
                addSystemMessage(`${file.name} exceeds ${CONFIG.MAX_FILE_SIZE_MB}MB limit`);
                return;
            }
            const ext = "." + file.name.split('.').pop().toLowerCase();
            if (!CONFIG.ALLOWED_EXTS.includes(ext)) {
                addSystemMessage(`${file.name}: Unsupported file type.`);
                return;
            }

            const id = generateUUID();
            state.stagedFiles.push({ id, file });
            renderFileChip(file, id);
        });
        e.target.value = '';
    }

    function renderFileChip(file, id) {
        const chip = document.createElement('div');
        chip.className = 'flex items-center bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 pr-1 text-xs text-zinc-300 animate-fade-in';
        chip.id = `file-chip-${id}`;
        chip.innerHTML = `<span class="max-w-[100px] truncate mr-1">${escapeHtml(file.name)}</span><button type="button" class="p-0.5 hover:text-red-400" data-file-id="${id}">✕</button>`;
        dom.filePreviewContainer.appendChild(chip);
    }

    function handleFileRemove(id) {
        state.stagedFiles = state.stagedFiles.filter(f => f.id !== id);
        const chip = document.getElementById(`file-chip-${id}`);
        if(chip) chip.remove();
    }

    function clearStagedFiles() {
        state.stagedFiles = [];
        dom.filePreviewContainer.innerHTML = '';
    }

    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    init();
});