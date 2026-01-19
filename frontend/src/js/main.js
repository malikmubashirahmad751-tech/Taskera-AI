document.addEventListener('DOMContentLoaded', () => {

    
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const PROD_URL = 'https://mubashir751-taskera-ai-backend.hf.space';
    const API_BASE_URL = isLocal ? 'http://127.0.0.1:7860' : PROD_URL; 

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
        requestQueue: new Set(),
        modalCallback: null 
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

        taskeraModal: document.getElementById('taskeraModal'),
        taskeraModalTitle: document.getElementById('taskeraModalTitle'),
        taskeraModalBody: document.getElementById('taskeraModalBody'),
        taskeraModalConfirm: document.getElementById('taskeraModalConfirm'),
        taskeraModalCancel: document.getElementById('taskeraModalCancel'),
        taskeraModalClose: document.getElementById('taskeraModalClose'),
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

    
    function setupEventListeners() {
        if (dom.menuButton) dom.menuButton.addEventListener('click', () => toggleSidebar());
        if (dom.sidebarOverlay) dom.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));

        if (dom.chatForm) dom.chatForm.addEventListener('submit', handleChatSubmit);
        if (dom.userInput) {
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

        if (dom.chatUploadBtn) dom.chatUploadBtn.addEventListener('click', () => {
            if (!state.isProcessing) dom.fileUploadInput.click();
        });
        if (dom.fileUploadInput) dom.fileUploadInput.addEventListener('change', handleFileStage);
        if (dom.filePreviewContainer) {
            dom.filePreviewContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('button[data-file-id]');
                if (btn) handleFileRemove(btn.dataset.fileId);
            });
        }

        if (dom.newSessionBtn) dom.newSessionBtn.addEventListener('click', handleNewSession);
        if (dom.openLoginModalBtn) dom.openLoginModalBtn.addEventListener('click', () => showAuthModal(true));
        if (dom.closeAuthModal) dom.closeAuthModal.addEventListener('click', hideAuthModal);
        if (dom.authSwitchBtn) dom.authSwitchBtn.addEventListener('click', toggleAuthMode);
        if (dom.authForm) dom.authForm.addEventListener('submit', handleAuthSubmit);
        if (dom.logoutBtn) dom.logoutBtn.addEventListener('click', handleLogout);

        if (dom.authModal) {
            dom.authModal.addEventListener('click', (e) => {
                if (e.target === dom.authModal) hideAuthModal();
            });
        }

        if (dom.taskeraModalCancel) dom.taskeraModalCancel.addEventListener('click', closeModal);
        if (dom.taskeraModalClose) dom.taskeraModalClose.addEventListener('click', closeModal);
        if (dom.taskeraModalConfirm) {
            dom.taskeraModalConfirm.addEventListener('click', () => {
                if (state.modalCallback) state.modalCallback();
            });
        }
        if (dom.taskeraModal) {
            dom.taskeraModal.addEventListener('click', (e) => {
                if (e.target === dom.taskeraModal) closeModal();
            });
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && dom.taskeraModal && !dom.taskeraModal.classList.contains('hidden')) {
                if (document.activeElement.id === 'renameInput') {
                    if (state.modalCallback) state.modalCallback();
                }
            }
        });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && state.authToken) {
                fetchHistory();
            }
        });

        document.addEventListener('click', () => {
            document.querySelectorAll('.history-dropdown').forEach(el => el.classList.add('hidden'));
        });
    }

    
    async function handleChatSubmit(e) {
        if (e) e.preventDefault();

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
            if (dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

            const formData = new FormData();
            formData.append('query', message);
            formData.append('user_id', state.currentUserId);
            if (state.currentThreadId) formData.append('thread_id', state.currentThreadId);

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
                if (response.status === 503 || response.status === 504) {
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

                if (!response.ok) throw new Error(data.detail?.message || data.error || `Error: ${response.status}`);

                if (data.thread_id) {
                    const isNewThread = !state.currentThreadId;
                    state.currentThreadId = data.thread_id;
                    if (isNewThread && state.authToken) setTimeout(() => fetchHistory(), 1500);
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
                    addSystemMessage("Request timed out");
                    return;
                }
                console.error('Chat error:', error);
                addSystemMessage(`Error: ${error.message}`);
            }
        } finally {
            setProcessing(false);
            state.requestQueue.delete(requestKey);
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
        dom.historyList.innerHTML = '';
        const fragment = document.createDocumentFragment();

        threads.forEach(thread => {
            const btnContainer = document.createElement('div');
            btnContainer.className = 'group relative mb-1 flex items-center pr-8';

            const btn = document.createElement('button');
            const isActive = state.currentThreadId === thread.thread_id;

            btn.className = `flex-1 text-left px-3 py-2 rounded-lg text-xs transition-colors truncate flex flex-col 
                ${isActive ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-white'}`;

            const date = new Date(thread.updated_at || thread.created_at)
                .toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

            btn.innerHTML = `
                <span class="block font-medium truncate w-[90%]">${escapeHtml(thread.title || 'Conversation')}</span>
                <span class="text-[10px] opacity-50">${date}</span>
            `;

            btn.onclick = () => loadThread(thread.thread_id);

            // Three Dot Menu Button
            const menuBtn = document.createElement('button');
            menuBtn.className = 'absolute right-1 top-1/2 transform -translate-y-1/2 text-zinc-500 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-zinc-700/50';
            menuBtn.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z"></path>
                </svg>
            `;

            const dropdown = document.createElement('div');
            dropdown.className = 'history-dropdown absolute right-0 top-full mt-1 w-32 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl z-50 hidden flex-col overflow-hidden';

            const renameOption = document.createElement('button');
            renameOption.className = 'w-full text-left px-4 py-2.5 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors border-b border-zinc-800/50 flex items-center';
            renameOption.innerHTML = `
                <svg class="w-3 h-3 mr-2 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                Rename
            `;
            renameOption.onclick = (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                openModal('rename', { threadId: thread.thread_id, currentTitle: thread.title });
            };

            const deleteOption = document.createElement('button');
            deleteOption.className = 'w-full text-left px-4 py-2.5 text-xs text-red-400 hover:bg-red-900/20 hover:text-red-300 transition-colors flex items-center';
            deleteOption.innerHTML = `
                <svg class="w-3 h-3 mr-2 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                Delete
            `;
            deleteOption.onclick = (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                openModal('delete', { threadId: thread.thread_id, currentTitle: thread.title, element: btnContainer });
            };

            dropdown.appendChild(renameOption);
            dropdown.appendChild(deleteOption);

            menuBtn.onclick = (e) => {
                e.stopPropagation();
                document.querySelectorAll('.history-dropdown').forEach(el => {
                    if (el !== dropdown) el.classList.add('hidden');
                });
                dropdown.classList.toggle('hidden');
            };

            btnContainer.appendChild(btn);
            btnContainer.appendChild(menuBtn);
            btnContainer.appendChild(dropdown);
            fragment.appendChild(btnContainer);
        });

        dom.historyList.appendChild(fragment);
    }

    async function loadThread(threadId) {
        if (state.currentThreadId === threadId) return;
        cancelOngoingRequest();
        state.currentThreadId = threadId;

        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        if (dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');
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

    function openModal(type, data = {}) {
        const modal = dom.taskeraModal;
        const content = modal.querySelector('.modal-content');

        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.classList.remove('opacity-0');
            content.classList.remove('opacity-0', 'scale-95');
        }, 10);

        if (type === 'rename') {
            dom.taskeraModalTitle.textContent = 'Rename Conversation';
            dom.taskeraModalBody.innerHTML = `
                <p class="text-zinc-400 mb-3 text-sm">Enter a new name for this chat.</p>
                <input type="text" id="renameInput" value="${escapeHtml(data.currentTitle)}" class="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-white focus:border-fuchsia-500 focus:outline-none text-sm" autocomplete="off">
            `;
            const input = document.getElementById('renameInput');
            setTimeout(() => input.focus(), 100);

            dom.taskeraModalConfirm.textContent = 'Rename';
            dom.taskeraModalConfirm.className = 'px-4 py-2 rounded-lg bg-white text-zinc-900 hover:bg-zinc-200 transition-colors text-sm font-bold shadow-lg shadow-white/10';

            state.modalCallback = () => handleRenameThread(data.threadId, input.value);
        } else if (type === 'delete') {
            dom.taskeraModalTitle.textContent = 'Delete Conversation';
            dom.taskeraModalBody.innerHTML = `
                <p class="text-zinc-300 text-sm">Are you sure you want to delete <span class="text-white font-medium">"${escapeHtml(data.currentTitle)}"</span>?</p>
                <p class="text-red-400/80 text-xs mt-2">This action cannot be undone.</p>
            `;
            dom.taskeraModalConfirm.textContent = 'Delete';
            dom.taskeraModalConfirm.className = 'px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-500 transition-colors text-sm font-bold shadow-lg shadow-red-900/20';

            state.modalCallback = () => handleDeleteThread(data.threadId, data.element);
        }
    }

    function closeModal() {
        const modal = dom.taskeraModal;
        const content = modal.querySelector('.modal-content');
        modal.classList.add('opacity-0');
        content.classList.add('opacity-0', 'scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
            dom.taskeraModalBody.innerHTML = '';
            state.modalCallback = null;
        }, 200);
    }

    async function handleRenameThread(threadId, newTitle) {
        if (!newTitle.trim()) return;
        const originalText = dom.taskeraModalConfirm.textContent;
        dom.taskeraModalConfirm.textContent = "Renaming...";
        dom.taskeraModalConfirm.disabled = true;

        try {
            const url = `${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${encodeURIComponent(state.currentUserId)}`;
            const response = await fetch(url, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${state.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ title: newTitle })
            });

            if (response.ok) {
                closeModal();
                fetchHistory();
                addSystemMessage("Conversation renamed successfully");
            } else {
                const err = await response.json();
                throw new Error(err.detail?.message || "Failed to rename");
            }
        } catch (e) {
            console.error("Rename failed", e);
            alert(`Failed to rename conversation: ${e.message}`);
        } finally {
            dom.taskeraModalConfirm.textContent = originalText;
            dom.taskeraModalConfirm.disabled = false;
        }
    }

    async function handleDeleteThread(threadId, element) {
        const originalText = dom.taskeraModalConfirm.textContent;
        dom.taskeraModalConfirm.textContent = "Deleting...";
        dom.taskeraModalConfirm.disabled = true;

        try {
            const url = `${API_BASE_URL}${ENDPOINTS.THREADS}/${threadId}?user_id=${encodeURIComponent(state.currentUserId)}`;
            const response = await fetch(url, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${state.authToken}` }
            });

            if (response.ok) {
                element.remove();
                if (state.currentThreadId === threadId) {
                    handleNewSession();
                }
                closeModal();
                addSystemMessage("Conversation deleted");
            } else {
                throw new Error("Failed to delete");
            }
        } catch (e) {
            console.error("Delete failed", e);
            alert("Failed to delete conversation.");
        } finally {
            dom.taskeraModalConfirm.textContent = originalText;
            dom.taskeraModalConfirm.disabled = false;
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
                addSystemMessage("Logged in!");
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
        if (dom.historySection) dom.historySection.classList.add('hidden');
        addSystemMessage("Logged out successfully");
    }

    function updateAuthUI(isLoggedIn, email = '') {
        if (isLoggedIn) {
            if (dom.guestAuthSection) dom.guestAuthSection.classList.add('hidden');
            if (dom.userProfileSection) dom.userProfileSection.classList.remove('hidden');
            if (dom.userEmailDisplay) dom.userEmailDisplay.textContent = email;
        } else {
            if (dom.guestAuthSection) dom.guestAuthSection.classList.remove('hidden');
            if (dom.userProfileSection) dom.userProfileSection.classList.add('hidden');
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
            if (dom.historySection) dom.historySection.classList.add('hidden');
        }

        if (dom.currentUserIdDisplay) {
            dom.currentUserIdDisplay.textContent = state.currentUserId.substring(0, 10) + '...';
        }
    }

    function showAuthModal(isLogin = true, msg = null) {
        state.isLoginMode = isLogin;
        renderAuthModalState();
        dom.authModal.classList.remove('hidden');
        setTimeout(() => {
            dom.authModal.classList.remove('opacity-0');
            const content = dom.authModal.querySelector('.modal-content');
            if (content) content.classList.remove('scale-95', 'opacity-0');
        }, 10);
        if (msg) showAuthError(msg);
    }

    function hideAuthModal() {
        dom.authModal.classList.add('opacity-0');
        const content = dom.authModal.querySelector('.modal-content');
        if (content) content.classList.add('scale-95', 'opacity-0');
        setTimeout(() => {
            dom.authModal.classList.add('hidden');
            dom.authErrorMsg.classList.add('hidden');
        }, 300);
    }

    function renderAuthModalState() {
        dom.authModalTitle.textContent = state.isLoginMode ? "Sign In" : "Create Account";
        dom.authSubmitBtn.textContent = state.isLoginMode ? "Sign In" : "Sign Up";
        dom.authSwitchText.textContent = state.isLoginMode ? "Don't have an account?" : "Already have an account?";
        dom.authSwitchBtn.textContent = state.isLoginMode ? "Sign Up" : "Sign In";
        dom.authErrorMsg.classList.add('hidden');
    }

    function toggleAuthMode(e) {
        e.preventDefault();
        state.isLoginMode = !state.isLoginMode;
        renderAuthModalState();
    }

    function showAuthError(msg) {
        dom.authErrorMsg.textContent = msg;
        dom.authErrorMsg.classList.remove('hidden', 'text-green-400', 'bg-green-900/10');
        dom.authErrorMsg.classList.add('text-red-400', 'bg-red-900/10');
        dom.authErrorMsg.classList.remove('hidden');
    }

    function showAuthSuccess(msg) {
        dom.authErrorMsg.textContent = msg;
        dom.authErrorMsg.classList.remove('hidden', 'text-red-400', 'bg-red-900/10');
        dom.authErrorMsg.classList.add('text-green-400', 'bg-green-900/10');
        dom.authErrorMsg.classList.remove('hidden');
    }

        function handleNewSession() {
        cancelOngoingRequest();
        dom.chatLog.querySelectorAll('.chat-message-wrapper').forEach(msg => msg.remove());
        if (dom.welcomeScreen) dom.welcomeScreen.classList.remove('hidden');
        clearStagedFiles();
        dom.userInput.value = '';
        dom.userInput.focus();
        toggleSidebar(false);
        state.retryCount = 0;
        state.currentThreadId = null;
        if (state.authToken) fetchHistory();
    }

    function toggleSidebar(force) {
        if (!dom.sidebar) return;
        const isOpen = !dom.sidebar.classList.contains('-translate-x-full');
        const newState = (typeof force === 'boolean') ? force : !isOpen;
        if (newState) {
            dom.sidebar.classList.remove('-translate-x-full');
            dom.sidebarOverlay.classList.remove('hidden');
            if (dom.menuIcon) dom.menuIcon.classList.add('hidden');
            if (dom.closeIcon) dom.closeIcon.classList.remove('hidden');
        } else {
            dom.sidebar.classList.add('-translate-x-full');
            dom.sidebarOverlay.classList.add('hidden');
            if (dom.menuIcon) dom.menuIcon.classList.remove('hidden');
            if (dom.closeIcon) dom.closeIcon.classList.add('hidden');
        }
    }

    function setProcessing(proc) {
        state.isProcessing = proc;
        dom.userInput.disabled = proc;
        dom.sendButton.disabled = proc;
        dom.chatUploadBtn.disabled = proc;
        dom.sendButton.innerHTML = proc ? `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>` : `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path></svg>`;
        if (!proc) dom.userInput.focus();
    }

    function updateUIState() {
        if (dom.welcomeScreen) {
            dom.chatLog.querySelectorAll('.chat-message-wrapper').length > 0 ? dom.welcomeScreen.classList.add('hidden') : dom.welcomeScreen.classList.remove('hidden');
        }
    }

    function handleFileStage(e) {
        const files = Array.from(e.target.files);
        if (state.stagedFiles.length + files.length > CONFIG.MAX_FILES) {
            addSystemMessage(`Max ${CONFIG.MAX_FILES} files.`);
            return;
        }
        files.forEach(file => {
            if (file.size / (1024 * 1024) > CONFIG.MAX_FILE_SIZE_MB) {
                addSystemMessage(`${file.name} too large.`);
                return;
            }
            const ext = "." + file.name.split('.').pop().toLowerCase();
            if (!CONFIG.ALLOWED_EXTS.includes(ext)) {
                addSystemMessage(`${file.name} unsupported.`);
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
        if (chip) chip.remove();
    }

    function clearStagedFiles() {
        state.stagedFiles = [];
        dom.filePreviewContainer.innerHTML = '';
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

    function setupOnlineDetection() {
        window.addEventListener('online', () => { state.isOnline = true; addSystemMessage("Connection restored"); });
        window.addEventListener('offline', () => { state.isOnline = false; addSystemMessage("You're offline. Messages will fail until reconnected."); });
    }

    async function checkServerHealth() {
        if (!state.isOnline) return;
        try {
            const response = await fetch(`${API_BASE_URL}${ENDPOINTS.HEALTH}`, { method: 'GET', signal: AbortSignal.timeout(5000) });
            if (!response.ok) console.warn("Server health check failed");
        } catch (e) {
            console.warn("Server unreachable:", e.message);
        }
    }


    function formatAIResponse(text) {
        if (!text) return '';
        let f = escapeHtml(text);
        f = f.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
        f = f.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-900 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-xs text-fuchsia-300">$1</code></pre>');
        f = f.replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1.5 py-0.5 rounded text-fuchsia-300 font-mono text-xs">$1</code>');
        f = f.replace(/^\s*[-*]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');
        f = f.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" class="text-fuchsia-400 hover:underline">$1</a>');
        return f.replace(/\n/g, '<br>');
    }

    function escapeHtml(u) { if (!u) return ''; return u.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
    function renderFileAttachments(n) { if (!n || !n.length) return ''; return `<div class="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">${n.map(x => `<div class="text-xs text-white/70 bg-black/20 px-2 py-1 rounded border border-white/5">${escapeHtml(x)}</div>`).join('')}</div>`; }

    function createMessageElement(sender, message, fileNames = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat-message-wrapper w-full flex ${sender === 'user' ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in`;
        if (sender === 'user') {
            wrapper.innerHTML = `<div class="flex flex-col items-end max-w-[85%] md:max-w-2xl"><div class="bg-zinc-800 text-white rounded-2xl rounded-tr-sm px-5 py-3.5 shadow-md border border-zinc-700/50"><p class="text-sm leading-relaxed whitespace-pre-wrap">${escapeHtml(message)}</p>${renderFileAttachments(fileNames)}</div></div>`;
        } else {
            wrapper.innerHTML = `<div class="flex items-start space-x-4 max-w-full md:max-w-3xl"><div class="flex-shrink-0 mt-1"><img src="assets/images/logo.png" class="w-8 h-8 rounded-lg shadow-sm" onerror="this.style.display='none'"></div><div class="flex-1 min-w-0"><div class="prose prose-invert prose-sm max-w-none text-zinc-300 leading-relaxed">${formatAIResponse(message)}</div></div></div>`;
        }
        return wrapper;
    }

    function addMessageToChat(sender, message, fn = null) { dom.chatLog.appendChild(createMessageElement(sender, message, fn)); scrollToBottom(); }
    function addSystemMessage(text) { const w = document.createElement('div'); w.className = 'chat-message-wrapper flex justify-center my-4 animate-fade-in'; w.innerHTML = `<span class="text-xs text-zinc-500 bg-zinc-900/50 border border-zinc-800 px-3 py-1 rounded-full">${escapeHtml(text)}</span>`; dom.chatLog.appendChild(w); scrollToBottom(); }

    function addTypingIndicator() {
        removeTypingIndicator();
        const w = document.createElement('div'); w.id = 'typing-indicator'; w.className = 'chat-message-wrapper flex items-start space-x-4 mb-6 animate-fade-in';
        w.innerHTML = `<div class="flex-shrink-0 mt-1"><img src="assets/images/logo.png" class="w-8 h-8 rounded-lg opacity-80" onerror="this.style.display='none'"></div><div class="flex items-center h-8"><div class="flex space-x-1.5 bg-zinc-900/50 px-3 py-2 rounded-xl border border-zinc-800"><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0s"></div><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div><div class="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div></div></div>`;
        dom.chatLog.appendChild(w); scrollToBottom();
    }

    function removeTypingIndicator() { const el = document.getElementById('typing-indicator'); if (el) el.remove(); }
    function scrollToBottom() { requestAnimationFrame(() => { dom.chatLog.scrollTop = dom.chatLog.scrollHeight; }); }
    function generateUUID() { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16); }); }

    init();
});