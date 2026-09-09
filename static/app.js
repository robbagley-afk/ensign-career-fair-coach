const modes = {
  research: {
    label: 'Employer research',
    opener: 'Tell me the employer and role you want to explore. We’ll find one role detail, one company detail, and a question worth asking.',
    prompts: ['Help me create Handshake account', 'Research company coming to fair', 'Resume help']
  },
  pitch: {
    label: 'Me in 30 Seconds',
    opener: 'Let’s build a natural Me in 30 Seconds. Share your name, career direction, one proof point, and the employer or role you are targeting.',
    prompts: ['Help me build a 30-second pitch for an IT support role.', 'Here is my draft pitch. Make it clearer and more natural.']
  },
  practice: {
    label: 'Recruiter practice',
    opener: 'I’ll play the recruiter. Share your Me in 30 Seconds, and I’ll ask one follow-up and give you useful feedback.',
    prompts: ['Be a recruiter from Enterprise Mobility and practice with me.', 'Ask me how I have used AI responsibly at work or school.']
  },
  questions: {
    label: 'Recruiter-ready questions',
    opener: 'Let’s choose a question that sounds curious, specific, and natural. Tell me the employer or the kind of role you want to ask about.',
    prompts: ['Give me a strong question about early-career development.', 'Help me personalize a question about company culture.']
  },
};

let mode = 'research';
let history = [];
let lastUserMessage = '';

const messages = document.querySelector('#messages');
const suggestions = document.querySelector('#suggestions');
const input = document.querySelector('#message-input');
const form = document.querySelector('#chat-form');
const label = document.querySelector('#mode-label');
const status = document.querySelector('#service-status');

// Voice Practice Elements (Practice Mode)
const voicePracticePanel = document.querySelector('#voice-practice-panel');
const btnVoiceRecord = document.querySelector('#btn-voice-record');
const btnVoiceStop = document.querySelector('#btn-voice-stop');
const btnVoiceSend = document.querySelector('#btn-voice-send');
const voiceWaveform = document.querySelector('#waveform');
const voiceTimer = document.querySelector('#voice-timer');
const voiceStatusText = document.querySelector('#voice-status-text');
const micIndicatorDot = document.querySelector('#mic-indicator .mic-dot');
const micStatusLabel = document.querySelector('#mic-status-label');

let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let micStream = null;
let recordTimerInterval = null;
let recordSeconds = 0;
let lastTranscribedText = '';

function createFeedbackButton(label, className) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `feedback-button ${className}`;
  btn.textContent = label;
  return btn;
}

function addFeedbackControls(messageArticle, responseId, questionText, answerText) {
  if (!responseId) return;

  const region = document.createElement('div');
  region.className = 'answer-feedback';
  region.setAttribute('aria-label', 'Response feedback');

  const prompt = document.createElement('p');
  prompt.className = 'feedback-prompt';
  prompt.textContent = 'Was this response helpful?';

  const controls = document.createElement('div');
  controls.className = 'feedback-controls';

  const upButton = createFeedbackButton('👍 Helpful', 'feedback-up');
  const downButton = createFeedbackButton('👎 Suggested Improvement', 'feedback-down');
  controls.append(upButton, downButton);

  const formEl = document.createElement('form');
  formEl.className = 'feedback-form';
  formEl.hidden = true;

  const commentLabel = document.createElement('label');
  commentLabel.textContent = 'How can this response be improved?';

  const commentInput = document.createElement('textarea');
  commentInput.rows = 3;
  commentInput.placeholder = 'Explain what was missing, incorrect, or how to phrase it better...';
  commentInput.required = true;

  const warning = document.createElement('p');
  warning.className = 'feedback-warning';
  warning.textContent = '🔒 Keep personal student or identifying information out of feedback.';

  const formActions = document.createElement('div');
  formActions.className = 'feedback-form-actions';
  const submitButton = createFeedbackButton('Submit Feedback', 'feedback-submit');
  submitButton.type = 'submit';
  const cancelButton = createFeedbackButton('Cancel', 'feedback-cancel');
  formActions.append(submitButton, cancelButton);

  formEl.append(commentLabel, commentInput, warning, formActions);

  const statusEl = document.createElement('p');
  statusEl.className = 'feedback-status';

  region.append(prompt, controls, formEl, statusEl);
  messageArticle.appendChild(region);

  let submitted = false;
  const setDisabled = (val) => {
    upButton.disabled = val;
    downButton.disabled = val;
    submitButton.disabled = val;
    cancelButton.disabled = val;
    commentInput.disabled = val;
  };

  const submitFeedback = async (payload) => {
    setDisabled(true);
    statusEl.textContent = 'Saving feedback…';
    try {
      const resp = await fetch('api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          response_id: responseId,
          mode: mode,
          question: questionText,
          answer: answerText,
          ...payload
        })
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Failed to save feedback.');
      }
      submitted = true;
      controls.hidden = true;
      formEl.hidden = true;
      prompt.hidden = true;
      statusEl.className = 'feedback-status feedback-success';
      statusEl.textContent = payload.rating === 'up'
        ? '✓ Thank you! Marked as helpful.'
        : '✓ Thank you! Your suggestion was saved.';
    } catch (err) {
      statusEl.className = 'feedback-status feedback-error';
      statusEl.textContent = err.message || 'Feedback could not be saved.';
      setDisabled(false);
    }
  };

  upButton.addEventListener('click', () => {
    if (!submitted) submitFeedback({ rating: 'up' });
  });

  downButton.addEventListener('click', () => {
    if (submitted) return;
    formEl.hidden = false;
    statusEl.textContent = '';
    commentInput.focus();
  });

  cancelButton.addEventListener('click', () => {
    formEl.hidden = true;
    statusEl.textContent = '';
  });

  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!submitted && commentInput.value.trim()) {
      submitFeedback({
        rating: 'down',
        comment: commentInput.value.trim()
      });
    }
  });
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatInlineMarkdown(escapedText) {
  let str = escapedText;
  str = str.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
  str = str.replace(/__([^_]+?)__/g, '<strong>$1</strong>');
  str = str.replace(/(?<![*\w])\*([^*]+?)\*(?![*\w])/g, '<em>$1</em>');
  str = str.replace(/(?<![_\w])_([^_]+?)_(?![_\w])/g, '<em>$1</em>');
  return str;
}

const KNOWN_LINK_MAP = [
  {
    regex: /https?:\/\/ensign\.joinhandshake\.com\/login\/?/i,
    label: 'Handshake'
  },
  {
    regex: /https?:\/\/www\.ensign\.edu\/creating-a-handshake-account\/?/i,
    label: 'Handshake Sign Up'
  },
  {
    regex: /https?:\/\/ensign\.joinhandshake\.com\/stu\/schools\/771\/?/i,
    label: 'Handshake'
  },
  {
    regex: /https?:\/\/ensign\.joinhandshake\.com[^\s<"]*/i,
    label: 'Handshake'
  },
  {
    regex: /https?:\/\/app\.joinhandshake\.com[^\s<"]*/i,
    label: 'Handshake'
  }
];

function formatMessageLinks(container) {
  const elements = Array.from(container.querySelectorAll('p, li, div'));
  for (let i = 0; i < elements.length; i++) {
    const el = elements[i];
    let html = el.innerHTML;

    // 1. Convert repetitive markdown links like [https://...](https://...) -> label or clean URL
    html = html.replace(/\[?(https?:\/\/[^\s\]\)]+?)\]?\((https?:\/\/[^\s\)]+?)\)/g, (match, u1, u2) => {
      const url = u2 || u1;
      for (const item of KNOWN_LINK_MAP) {
        if (item.regex.test(url)) {
          return `[${item.label}](${url})`;
        }
      }
      return url;
    });

    // 2. Convert standard markdown links [Text Label](https://...) -> clickable link
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, (match, label, rawUrl) => {
      const cleanUrl = rawUrl.replace(/\/+$/, '');
      return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`;
    });

    // 3. Convert known bare URLs into friendly labeled links
    KNOWN_LINK_MAP.forEach(({ regex, label }) => {
      const safeRegex = new RegExp('(?<!href=["\']|">)' + regex.source, 'gi');
      html = html.replace(safeRegex, (match) => {
        const cleanUrl = match.replace(/\/+$/, '');
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`;
      });
    });

    // 4. Convert any remaining unlinked raw URLs into clean links
    html = html.replace(/(?<!href=["'])(https?:\/\/[^\s<"']+?)([.,;:)\]]*)(?=\s|$|<|")/g, (match, rawUrl, trail) => {
      const cleanUrl = rawUrl.replace(/\/+$/, '');
      return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${cleanUrl} ↗</a>${trail}`;
    });

    el.innerHTML = html;
  }
}

function renderMessageMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  let inList = false;
  let listType = null;
  const htmlParts = [];

  function closeList() {
    if (inList) {
      htmlParts.push(`</${listType}>`);
      inList = false;
      listType = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      closeList();
      continue;
    }

    const ulMatch = line.match(/^[-*•]\s+(.+)$/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        closeList();
        htmlParts.push('<ul class="message-list">');
        inList = true;
        listType = 'ul';
      }
      const itemText = formatInlineMarkdown(escapeHtml(ulMatch[1].trim()));
      htmlParts.push(`<li>${itemText}</li>`);
      continue;
    }

    const olMatch = line.match(/^(\d+)\.\s+(.+)$/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        closeList();
        htmlParts.push('<ol class="message-list">');
        inList = true;
        listType = 'ol';
      }
      const itemText = formatInlineMarkdown(escapeHtml(olMatch[2].trim()));
      htmlParts.push(`<li>${itemText}</li>`);
      continue;
    }

    closeList();
    const pText = formatInlineMarkdown(escapeHtml(line));
    htmlParts.push(`<p>${pText}</p>`);
  }

  closeList();
  return htmlParts.join('');
}

function addMessage(role, text, responseId = null, questionText = '') {
  const item = document.createElement('article');
  item.className = `message ${role}`;
  item.innerHTML = `<small>${role === 'assistant' ? 'Career Fair Coach' : 'You'}</small>`;
  const content = document.createElement('div');
  content.className = 'message-content';
  content.innerHTML = renderMessageMarkdown(text);
  formatMessageLinks(content);
  item.appendChild(content);

  if (role === 'assistant' && responseId) {
    addFeedbackControls(item, responseId, questionText, text);
  }

  messages.appendChild(item);
  
  // Smooth auto-scroll so latest response is immediately visible
  requestAnimationFrame(() => {
    messages.scrollTop = messages.scrollHeight;
    item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
}

function setMode(nextMode) {
  mode = nextMode;
  if (label && modes[mode]) {
    label.textContent = modes[mode].label;
  }
  document.querySelectorAll('.step-btn, .mode').forEach((button) => {
    button.classList.toggle('active', button.dataset.mode === mode);
  });
  messages.innerHTML = '';
  history = [];
  lastUserMessage = '';

  // Show voice practice panel specifically on Step 3: Practice
  if (voicePracticePanel) {
    if (mode === 'practice') {
      voicePracticePanel.hidden = false;
      resetVoiceState();
    } else {
      voicePracticePanel.hidden = true;
      stopVoiceRecording();
    }
  }

  if (modes[mode]) {
    addMessage('assistant', modes[mode].opener);
    suggestions.innerHTML = '';
    modes[mode].prompts.forEach((prompt) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = prompt;
      button.addEventListener('click', () => {
        input.value = prompt;
        input.focus();
        if (input.scrollHeight > input.clientHeight) {
          input.style.height = `${Math.min(input.scrollHeight, 90)}px`;
        }
      });
      suggestions.appendChild(button);
    });
  }
}

// ---------------------------------------------------------------------------
// Voice Recording and Transcription Logic (Modeled after Interview Practice)
// ---------------------------------------------------------------------------

function updateVoiceTimer() {
  recordSeconds++;
  const mins = String(Math.floor(recordSeconds / 60)).padStart(2, '0');
  const secs = String(recordSeconds % 60).padStart(2, '0');
  if (voiceTimer) {
    voiceTimer.textContent = `${mins}:${secs} (Target: ~30s)`;
  }
}

function resetVoiceState() {
  if (recordTimerInterval) {
    clearInterval(recordTimerInterval);
    recordTimerInterval = null;
  }
  recordSeconds = 0;
  if (voiceTimer) voiceTimer.textContent = '00:00 (Target: ~30s)';
  if (btnVoiceRecord) btnVoiceRecord.disabled = false;
  if (btnVoiceStop) btnVoiceStop.disabled = true;
  if (btnVoiceSend) btnVoiceSend.disabled = true;
  if (voiceWaveform) voiceWaveform.classList.remove('active');
  if (micIndicatorDot) micIndicatorDot.className = 'mic-dot';
  if (micStatusLabel) micStatusLabel.textContent = 'Mic Ready';
  if (voiceStatusText) {
    voiceStatusText.className = 'voice-status-text';
    voiceStatusText.textContent = '';
  }
}

async function startVoiceRecording() {
  audioChunks = [];
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(micStream);

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstart = () => {
      isRecording = true;
      btnVoiceRecord.disabled = true;
      btnVoiceStop.disabled = false;
      btnVoiceSend.disabled = true;
      micIndicatorDot.className = 'mic-dot recording';
      micStatusLabel.textContent = 'Recording…';
      voiceWaveform.classList.add('active');
      voiceStatusText.className = 'voice-status-text working';
      voiceStatusText.textContent = '🎙️ Recording your 30-second pitch… Speak clearly into your mic.';
      recordSeconds = 0;
      updateVoiceTimer();
      recordTimerInterval = setInterval(updateVoiceTimer, 1000);
    };

    mediaRecorder.onstop = async () => {
      isRecording = false;
      btnVoiceRecord.disabled = false;
      btnVoiceStop.disabled = true;
      micIndicatorDot.className = 'mic-dot';
      micStatusLabel.textContent = 'Processing';
      voiceWaveform.classList.remove('active');
      if (recordTimerInterval) {
        clearInterval(recordTimerInterval);
        recordTimerInterval = null;
      }

      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      await uploadVoiceForTranscription(audioBlob);
    };

    mediaRecorder.start(1000);
  } catch (err) {
    console.error('Microphone access error:', err);
    micStatusLabel.textContent = 'Mic Error';
    voiceStatusText.className = 'voice-status-text error';
    voiceStatusText.textContent = '⚠️ Could not access microphone. Please allow microphone permissions in your browser or type your pitch below.';
    resetVoiceState();
  }
}

function stopVoiceRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
}

async function uploadVoiceForTranscription(audioBlob) {
  voiceStatusText.className = 'voice-status-text working';
  voiceStatusText.textContent = '⏳ Transcribing your pitch locally with Whisper… Please wait.';
  btnVoiceRecord.disabled = true;
  btnVoiceStop.disabled = true;
  btnVoiceSend.disabled = true;

  const formData = new FormData();
  formData.append('audio', audioBlob, 'pitch.webm');

  try {
    const resp = await fetch('api/transcribe', {
      method: 'POST',
      body: formData
    });

    if (!resp.ok) {
      throw new Error(`Server returned error: ${resp.statusText}`);
    }

    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    let rawText = data.transcript || '';
    rawText = rawText.replace(/\[\d{2}:\d{2}\] Speaker: /g, '').trim();

    if (!rawText) {
      throw new Error('Transcription returned an empty response. Try speaking louder or typing.');
    }

    lastTranscribedText = rawText;
    input.value = rawText;
    input.style.height = `${Math.min(input.scrollHeight, 90)}px`;
    input.focus();

    btnVoiceSend.disabled = false;
    micStatusLabel.textContent = 'Ready';
    voiceStatusText.className = 'voice-status-text';
    voiceStatusText.textContent = '✓ Transcribed! Your pitch is in the "Chat Here" box below. Edit if needed, then click either Send button.';
  } catch (err) {
    console.error('Transcription error:', err);
    micStatusLabel.textContent = 'Transcribe Failed';
    voiceStatusText.className = 'voice-status-text error';
    voiceStatusText.textContent = `Transcription failed (${err.message}). You can type your pitch directly into the box below.`;
  } finally {
    btnVoiceRecord.disabled = false;
  }
}

if (btnVoiceRecord) {
  btnVoiceRecord.addEventListener('click', () => startVoiceRecording());
}

if (btnVoiceStop) {
  btnVoiceStop.addEventListener('click', () => stopVoiceRecording());
}

if (btnVoiceSend) {
  btnVoiceSend.addEventListener('click', () => {
    const textToSend = input.value.trim() || lastTranscribedText.trim();
    if (textToSend) {
      input.value = '';
      input.style.height = '44px';
      btnVoiceSend.disabled = true;
      voiceStatusText.textContent = '';
      submitMessage(textToSend);
    }
  });
}

async function submitMessage(message) {
  lastUserMessage = message;
  addMessage('user', message);
  history.push({ role: 'user', content: message });
  status.textContent = 'Thinking…';
  try {
    const response = await fetch('api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, mode, history })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Something went wrong.');
    addMessage('assistant', data.reply, data.response_id, lastUserMessage);
    if (data.live) {
      status.textContent = data.engine === 'qwen' ? 'AI live (Qwen fallback)' : 'AI coaching live';
    } else {
      status.textContent = 'Career Fair Coach Python Engine';
    }
  } catch (error) {
    addMessage('assistant', error.message || 'I hit a snag. Please try again.');
    status.textContent = 'Try again';
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  input.style.height = '44px';
  await submitMessage(message);
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.dispatchEvent(new Event('submit', { cancelable: true }));
  }
});

input.addEventListener('input', () => {
  input.style.height = '44px';
  if (input.scrollHeight > 44) {
    input.style.height = `${Math.min(input.scrollHeight, 90)}px`;
  }
  if (btnVoiceSend && mode === 'practice') {
    btnVoiceSend.disabled = input.value.trim().length === 0;
  }
});

document.querySelectorAll('.step-btn, .mode').forEach((button) => {
  button.addEventListener('click', () => setMode(button.dataset.mode));
});

const newChatBtn = document.querySelector('#new-chat');
if (newChatBtn) {
  newChatBtn.addEventListener('click', () => setMode(mode));
}

setMode(mode);

