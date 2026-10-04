const state = {
  token: localStorage.getItem('telegram-token') || '',
  user: null,
  channels: [],
  activeChannelId: null,
};

const ui = {
  authPanel: document.getElementById('authPanel'),
  channelList: document.getElementById('channelList'),
  loginForm: document.getElementById('loginForm'),
  registerForm: document.getElementById('registerForm'),
  authTabs: document.querySelectorAll('.auth-tab'),
  newChannelBtn: document.getElementById('newChannelBtn'),
  chatPanel: document.getElementById('chatPanel'),
  chatTitle: document.getElementById('chatTitle'),
  chatStatus: document.getElementById('chatStatus'),
  messages: document.getElementById('messages'),
  composer: document.getElementById('composer'),
  composerInput: document.getElementById('composerInput'),
  fileInput: document.getElementById('messageFile'),
  logoutBtn: document.getElementById('logoutBtn'),
};

function setAuthTab(tab) {
  ui.authTabs.forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  ui.loginForm.classList.toggle('hidden', tab !== 'login');
  ui.registerForm.classList.toggle('hidden', tab !== 'register');
}

async function api(path, options = {}) {
  const { method = 'GET', body = null, isJson = true } = options;
  const headers = new Headers();
  
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (isJson && body && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { method, headers, body });
  const text = await response.text();
  let data = {};
  
  try {
    data = text ? JSON.parse(text) : {};
  } catch (e) {
    console.error('JSON parse error:', text);
    throw new Error('Invalid server response');
  }

  if (!response.ok) throw new Error(data.detail || `Error: ${response.status}`);
  return data;
}

function getAvatar(user) {
  if (user?.avatar_url) return user.avatar_url;
  return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(user?.username || 'user')}`;
}

function escape(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatTime(isoTime) {
  if (!isoTime) return '';
  return new Date(isoTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function renderChannels() {
  ui.channelList.innerHTML = '';
  state.channels.forEach(ch => {
    const btn = document.createElement('button');
    btn.className = `channel-item ${ch.id === state.activeChannelId ? 'active' : ''}`;
    btn.type = 'button';
    btn.innerHTML = `
      <div class="channel-badge">${escape(ch.name.slice(0, 2).toUpperCase())}</div>
      <div class="channel-meta">
        <div class="channel-name">${escape(ch.name)}</div>
        <div class="channel-desc">${escape(ch.description || 'No description')}</div>
      </div>
    `;
    btn.onclick = () => selectChannel(ch.id);
    ui.channelList.appendChild(btn);
  });
}

function renderMessages(msgs) {
  if (!msgs.length) {
    ui.messages.innerHTML = '<div class="message-row"><div class="message-bubble"><div class="message-text">Channel is empty. Start chatting!</div></div></div>';
    return;
  }

  ui.messages.innerHTML = msgs.map(msg => {
    const sender = msg.user || {};
    const avatar = getAvatar(sender);
    const name = escape(sender.display_name || sender.username || 'Unknown');
    const text = msg.text ? `<div class="message-text">${escape(msg.text)}</div>` : '';
    let media = '';
    
    if (msg.media_type === 'image' && msg.media_url) {
      media = `<div class="message-media"><img src="${msg.media_url}" alt="image"></div>`;
    } else if (msg.media_type === 'video' && msg.media_url) {
      media = `<div class="message-media"><video controls src="${msg.media_url}"></video></div>`;
    } else if (msg.media_type === 'audio' && msg.media_url) {
      media = `<div class="message-media"><audio controls src="${msg.media_url}"></audio></div>`;
    } else if (msg.media_type === 'file' && msg.media_url) {
      media = `<div class="message-media"><a href="${msg.media_url}" target="_blank" class="secondary-button">Download file</a></div>`;
    }
    
    return `
      <div class="message-row">
        <img class="user-avatar" src="${avatar}" alt="${name}">
        <div class="message-bubble">
          <div class="message-author">${name}</div>
          ${text}
          ${media}
          <div class="message-time">${formatTime(msg.created_at)}</div>
        </div>
      </div>
    `;
  }).join('');

  ui.messages.scrollTop = ui.messages.scrollHeight;
}

async function selectChannel(id) {
  state.activeChannelId = id;
  renderChannels();
  try {
    const msgs = await api(`/api/channels/${id}/messages`);
    const ch = state.channels.find(c => c.id === id);
    ui.chatTitle.textContent = ch.name;
    ui.chatStatus.textContent = `${ch.description || 'Channel'} • ${msgs.length} messages`;
    renderMessages(msgs);
  } catch (e) {
    alert('Error loading messages: ' + e.message);
  }
}

async function loadChannels() {
  try {
    state.channels = await api('/api/channels');
    if (!state.activeChannelId && state.channels.length) {
      state.activeChannelId = state.channels[0].id;
    }
    renderChannels();
    if (state.activeChannelId) {
      await selectChannel(state.activeChannelId);
    }
  } catch (e) {
    console.error('Error loading channels:', e);
  }
}

async function createChannel() {
  const name = prompt('Channel name:');
  if (!name?.trim()) return;
  try {
    const fd = new FormData();
    fd.append('name', name);
    fd.append('description', 'New channel');
    const ch = await api('/api/channels', { method: 'POST', body: fd, isJson: false });
    state.channels.push(ch);
    state.activeChannelId = ch.id;
    renderChannels();
    await selectChannel(ch.id);
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function login(e) {
  e.preventDefault();
  const fd = new FormData(ui.loginForm);
  try {
    const res = await api('/api/login', { method: 'POST', body: fd, isJson: false });
    state.token = res.token;
    state.user = res.user;
    localStorage.setItem('telegram-token', res.token);
    showChat();
    await loadChannels();
  } catch (e) {
    alert('Login failed: ' + e.message);
  }
}

async function register(e) {
  e.preventDefault();
  const fd = new FormData(ui.registerForm);
  try {
    const res = await api('/api/register', { method: 'POST', body: fd, isJson: false });
    state.token = res.token;
    state.user = res.user;
    localStorage.setItem('telegram-token', res.token);
    showChat();
    await loadChannels();
  } catch (e) {
    alert('Register failed: ' + e.message);
  }
}

async function sendMessage(e) {
  e.preventDefault();
  if (!state.activeChannelId) return;
  
  const fd = new FormData();
  const text = ui.composerInput.value.trim();
  if (text) fd.append('text', text);
  
  const file = ui.fileInput.files[0];
  if (file) fd.append('file', file);
  
  if (!text && !file) return;
  
  try {
    await api(`/api/channels/${state.activeChannelId}/messages`, {
      method: 'POST',
      body: fd,
      isJson: false
    });
    ui.composerInput.value = '';
    ui.fileInput.value = '';
    await selectChannel(state.activeChannelId);
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function logout() {
  localStorage.removeItem('telegram-token');
  state.token = '';
  state.user = null;
  state.channels = [];
  state.activeChannelId = null;
  ui.loginForm.reset();
  ui.registerForm.reset();
  showAuth();
}

function showAuth() {
  ui.authPanel.classList.remove('hidden');
  ui.channelList.classList.add('hidden');
  ui.chatPanel.classList.add('hidden');
  ui.logoutBtn.classList.add('hidden');
}

function showChat() {
  ui.authPanel.classList.add('hidden');
  ui.channelList.classList.remove('hidden');
  ui.chatPanel.classList.remove('hidden');
  ui.logoutBtn.classList.remove('hidden');
}

async function init() {
  ui.authTabs.forEach(tab => {
    tab.addEventListener('click', () => setAuthTab(tab.dataset.tab));
  });
  
  ui.loginForm.addEventListener('submit', login);
  ui.registerForm.addEventListener('submit', register);
  ui.newChannelBtn.addEventListener('click', createChannel);
  ui.composer.addEventListener('submit', sendMessage);
  ui.logoutBtn.addEventListener('click', logout);
  
  setAuthTab('login');
  
  if (state.token) {
    try {
      const me = await api('/api/me');
      state.user = me.user;
      showChat();
      await loadChannels();
    } catch (e) {
      console.error('Session error:', e);
      logout();
    }
  }
}

init();