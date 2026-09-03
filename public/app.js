const modes = {
  research: {
    label: 'Employer research',
    opener: 'Tell me the employer and role you want to explore. We’ll find one role detail, one company detail, and a question worth asking.',
    prompts: ['Help me research Enterprise Mobility for a management trainee role.', 'What should I look for in a Handshake listing?']
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

function addMessage(role, text, responseId = null, questionText = '') {
  const item = document.createElement('article');
  item.className = `message ${role}`;
  item.innerHTML = `<small>${role === 'assistant' ? 'Career Fair Coach' : 'You'}</small>`;
  const content = document.createElement('div');
  content.textContent = text;
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
    history.push({ role: 'assistant', content: data.reply });
    status.textContent = data.live ? 'AI coaching live' : 'Helpful fallback';
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
});

document.querySelectorAll('.step-btn, .mode').forEach((button) => {
  button.addEventListener('click', () => setMode(button.dataset.mode));
});

const newChatBtn = document.querySelector('#new-chat');
if (newChatBtn) {
  newChatBtn.addEventListener('click', () => setMode(mode));
}

setMode(mode);
