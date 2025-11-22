// Admin Dashboard JavaScript
let currentPage = 1;
let totalPages = 1;
let currentConversationId = null;
let currentTurnNumber = null;
let conversationEvaluations = {}; // Cache for AI evaluations

// Switch between tabs
function switchTab(tabName) {
  // Hide all tabs
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  
  // Show selected tab
  document.getElementById(`${tabName}-tab`).classList.add('active');
  event.target.classList.add('active');
  
  // Load content for tab
  if (tabName === 'conversations') loadConversations();
  else if (tabName === 'analytics') loadAnalytics();
  else if (tabName === 'approved') loadApprovedResponses();
}

// Load conversations list
async function loadConversations() {
  const channel = document.getElementById('channel-filter').value;
  const startDate = document.getElementById('start-date').value;
  const endDate = document.getElementById('end-date').value;
  const needsReview = document.getElementById('needs-review-filter')?.checked || false;
  
  const params = new URLSearchParams({
    page: currentPage,
    page_size: 20
  });
  if (channel) params.append('channel', channel);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  
  try {
    const response = await fetch(`/admin/api/conversations?${params}`);
    const data = await response.json();
    
    // Load AI evaluations for each conversation
    const conversations = data.conversations;
    await Promise.all(conversations.map(conv => loadEvaluation(conv.id)));
    
    // Filter by needs_review if checkbox is checked
    let filteredConversations = conversations;
    if (needsReview) {
      filteredConversations = conversations.filter(conv => {
        const eval = conversationEvaluations[conv.id];
        return eval && eval.needs_review;
      });
    }
    
    totalPages = Math.ceil(filteredConversations.length / 20);
    displayConversations(filteredConversations);
    updatePagination();
  } catch (error) {
    console.error('Error loading conversations:', error);
    alert('Error loading conversations');
  }
}

// Display conversations
function displayConversations(conversations) {
  const container = document.getElementById('conversations-list');
  
  if (conversations.length === 0) {
    container.innerHTML = '<p class="empty">No conversations found</p>';
    return;
  }
  
  container.innerHTML = conversations.map(conv => {
    const evaluation = conversationEvaluations[conv.id];
    const priorityBadge = evaluation ? getPriorityBadge(evaluation.priority, evaluation.overall_score) : '';
    
    return `
    <div class="conversation-card" onclick="viewConversation('${conv.id}')">
      <div class="conv-header">
        <span class="conv-id">${conv.id}</span>
        <span class="conv-channel ${conv.channel}">${conv.channel}</span>
        ${conv.pii_detected ? '<span class="pii-badge">🔒 PII</span>' : ''}
        ${priorityBadge}
      </div>
      <div class="conv-meta">
        <span>📅 ${new Date(conv.timestamp).toLocaleString('it-IT')}</span>
        <span>💬 ${conv.total_turns} turns</span>
        <span>⏱️ ${conv.duration_seconds}s</span>
        ${evaluation ? `<span>🤖 AI Score: ${evaluation.overall_score}/10</span>` : ''}
      </div>
    </div>
    `;
  }).join('');
}

// View conversation detail
async function viewConversation(conversationId) {
  try {
    const response = await fetch(`/admin/api/conversations/${conversationId}`);
    const conv = await response.json();
    
    // Get AI evaluation for this conversation
    const evaluation = conversationEvaluations[conversationId];
    
    const modal = document.getElementById('conversation-modal');
    const detailDiv = document.getElementById('conversation-detail');
    
    detailDiv.innerHTML = `
      <div class="conv-info">
        <p><strong>ID:</strong> ${conv.id}</p>
        <p><strong>Channel:</strong> ${conv.channel}</p>
        <p><strong>Date:</strong> ${new Date(conv.timestamp).toLocaleString('it-IT')}</p>
        <p><strong>Turns:</strong> ${conv.turns.length}</p>
        ${conv.pii_detected_types && conv.pii_detected_types.length > 0 ? 
          `<p><strong>PII Detected:</strong> ${conv.pii_detected_types.join(', ')}</p>` : ''}
        ${evaluation ? `
          <div class="ai-evaluation-summary">
            <p><strong>🤖 AI Evaluation:</strong></p>
            <p>Overall Score: <strong>${evaluation.overall_score}/10</strong></p>
            <p>Priority: ${getPriorityBadge(evaluation.priority, evaluation.overall_score)}</p>
            <p>Needs Review: ${evaluation.needs_review ? '✅ Yes' : '❌ No'}</p>
            ${evaluation.critical_turns && evaluation.critical_turns.length > 0 ? 
              `<p>Critical Turns: ${evaluation.critical_turns.join(', ')}</p>` : ''}
          </div>
        ` : `
          <button onclick="evaluateSingleConversation('${conv.id}')" class="eval-btn">
            🤖 Evaluate with AI
          </button>
        `}
      </div>
      
      <div class="turns">
        ${conv.turns.map(turn => {
          const turnEval = evaluation?.turn_evaluations?.find(e => e.turn_number === turn.turn_number);
          const turnEvalData = turnEval?.evaluation;
          
          return `
          <div class="turn ${turnEvalData?.needs_review ? 'needs-review' : ''}">
            <div class="turn-header">
              <span>Turn ${turn.turn_number}</span>
              ${turnEvalData ? getPriorityBadge(turnEvalData.priority, turnEvalData.overall_score) : ''}
              <button onclick="openFeedbackModal('${conv.id}', ${turn.turn_number})" class="feedback-btn">
                💬 Feedback
              </button>
            </div>
            ${turnEvalData ? `
              <div class="ai-turn-evaluation">
                <p><strong>🤖 AI Analysis:</strong> Score ${turnEvalData.overall_score}/10</p>
                ${turnEvalData.evaluation_summary ? `<p><em>${turnEvalData.evaluation_summary}</em></p>` : ''}
                ${turnEvalData.issues && turnEvalData.issues.length > 0 ? `
                  <p><strong>Issues:</strong> ${turnEvalData.issues.join(', ')}</p>
                ` : ''}
                ${turnEvalData.strengths && turnEvalData.strengths.length > 0 ? `
                  <p><strong>Strengths:</strong> ${turnEvalData.strengths.join(', ')}</p>
                ` : ''}
                <details>
                  <summary>Category Scores</summary>
                  <ul>
                    ${Object.entries(turnEvalData.categories || {}).map(([cat, score]) => 
                      `<li>${cat}: ${score}/10</li>`
                    ).join('')}
                  </ul>
                </details>
              </div>
            ` : ''}
            <div class="message user-message">
              <strong>User:</strong> ${turn.user_message}
            </div>
            <div class="message bot-message">
              <strong>Bot:</strong> ${turn.bot_response}
            </div>
            ${turn.search_used ? `
              <div class="search-info">
                🔍 Search used: "${turn.search_query || 'N/A'}"
              </div>
            ` : ''}
          </div>
        `}).join('')}
      </div>
    `;
    
    modal.style.display = 'block';
  } catch (error) {
    console.error('Error loading conversation:', error);
    alert('Error loading conversation details');
  }
}

// Evaluate a single conversation and reload view
async function evaluateSingleConversation(conversationId) {
  const evaluation = await evaluateConversation(conversationId);
  if (evaluation) {
    // Check if there was an error in the evaluation
    if (evaluation.error) {
      alert(`⚠️ Evaluation completed with issues:\n\n${evaluation.error}\n\nScore: ${evaluation.overall_score}/10`);
    } else {
      alert('✅ Conversation evaluated successfully!');
    }
    viewConversation(conversationId); // Reload the view
  } else {
    alert('❌ Error: Unable to evaluate conversation. Check server logs for details.');
  }
}

// Close modal
function closeModal() {
  document.getElementById('conversation-modal').style.display = 'none';
}

// Open feedback modal
function openFeedbackModal(conversationId, turnNumber) {
  currentConversationId = conversationId;
  currentTurnNumber = turnNumber;
  
  // Reset form
  document.getElementById('selected-rating').value = '3';
  document.getElementById('admin-comment').value = '';
  document.getElementById('corrected-response').value = '';
  document.querySelectorAll('.tags input').forEach(cb => cb.checked = false);
  
  document.getElementById('feedback-modal').style.display = 'block';
}

// Close feedback modal
function closeFeedbackModal() {
  document.getElementById('feedback-modal').style.display = 'none';
}

// Set rating
function setRating(rating) {
  document.getElementById('selected-rating').value = rating;
  document.querySelectorAll('.rating button').forEach((btn, idx) => {
    btn.style.opacity = idx < rating ? '1' : '0.3';
  });
}

// Submit feedback
async function submitFeedback() {
  const rating = parseInt(document.getElementById('selected-rating').value);
  const comment = document.getElementById('admin-comment').value;
  const corrected = document.getElementById('corrected-response').value;
  
  const tags = [];
  document.querySelectorAll('.tags input:checked').forEach(cb => {
    tags.push(cb.value);
  });
  
  try {
    const response = await fetch(`/admin/api/feedback/${currentConversationId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        conversation_id: currentConversationId,
        turn_number: currentTurnNumber,
        rating,
        tags,
        admin_comment: comment,
        corrected_response: corrected
      })
    });
    
    if (response.ok) {
      alert('Feedback submitted successfully!');
      closeFeedbackModal();
    } else {
      alert('Error submitting feedback');
    }
  } catch (error) {
    console.error('Error submitting feedback:', error);
    alert('Error submitting feedback');
  }
}

// Approve response for learning
async function approveResponse() {
  if (!confirm('Approve this response for bot learning?')) return;
  
  try {
    const response = await fetch(`/admin/api/approve/${currentConversationId}/${currentTurnNumber}`, {
      method: 'POST'
    });
    
    if (response.ok) {
      alert('Response approved and indexed for learning!');
      closeFeedbackModal();
    } else {
      alert('Error approving response');
    }
  } catch (error) {
    console.error('Error approving response:', error);
    alert('Error approving response');
  }
}

// Load analytics
async function loadAnalytics() {
  try {
    const response = await fetch('/admin/api/analytics/dashboard');
    const data = await response.json();
    
    const container = document.getElementById('analytics-content');
    container.innerHTML = `
      <div class="metric-card">
        <h3>Total Conversations</h3>
        <p class="metric-value">${data.conversations?.total_conversations || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Avg Turns/Conv</h3>
        <p class="metric-value">${data.conversations?.avg_turns_per_conversation || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Total Feedback</h3>
        <p class="metric-value">${data.feedback?.total_feedback || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Avg Rating</h3>
        <p class="metric-value">${data.feedback?.avg_rating || 0} ⭐</p>
      </div>
      <div class="metric-card">
        <h3>Approved Responses</h3>
        <p class="metric-value">${data.approved_responses?.total_approved || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Search Usage</h3>
        <p class="metric-value">${data.conversations?.search_usage?.conversations_with_search || 0}</p>
      </div>
    `;
  } catch (error) {
    console.error('Error loading analytics:', error);
  }
}

// Pagination
function previousPage() {
  if (currentPage > 1) {
    currentPage--;
    loadConversations();
  }
}

function nextPage() {
  if (currentPage < totalPages) {
    currentPage++;
    loadConversations();
  }
}

function updatePagination() {
  document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages}`;
  document.getElementById('prev-page').disabled = currentPage === 1;
  document.getElementById('next-page').disabled = currentPage === totalPages;
}

// Load AI evaluation for a conversation
async function loadEvaluation(conversationId) {
  try {
    const response = await fetch(`/admin/api/evaluations/${conversationId}`);
    if (response.ok) {
      const evaluation = await response.json();
      conversationEvaluations[conversationId] = evaluation;
    }
  } catch (error) {
    // Evaluation not found or error - silently continue
  }
}

// Evaluate a single conversation
async function evaluateConversation(conversationId) {
  try {
    const response = await fetch(`/admin/api/evaluate/${conversationId}`, {
      method: 'POST'
    });
    
    if (response.ok) {
      const evaluation = await response.json();
      conversationEvaluations[conversationId] = evaluation;
      return evaluation;
    } else {
      // Try to get error message from response
      const errorData = await response.json().catch(() => ({}));
      console.error(`Error evaluating conversation ${conversationId}:`, errorData);
      console.error(`Status: ${response.status} ${response.statusText}`);
      
      // Show detailed error to user
      if (errorData.error) {
        alert(`⚠️ Evaluation Error:\n\n${errorData.error}`);
      }
    }
  } catch (error) {
    console.error(`Error evaluating conversation ${conversationId}:`, error);
  }
  return null;
}

// Evaluate all visible conversations
async function evaluateAllConversations() {
  if (!confirm('Evaluate all conversations with AI? This may take a few moments.')) {
    return;
  }
  
  const container = document.getElementById('conversations-list');
  const cards = container.querySelectorAll('.conversation-card');
  
  let evaluated = 0;
  for (const card of cards) {
    const convId = card.querySelector('.conv-id').textContent;
    
    // Skip if already evaluated recently
    const existing = conversationEvaluations[convId];
    if (existing && existing.timestamp) {
      const evalTime = new Date(existing.timestamp);
      const hoursSince = (Date.now() - evalTime.getTime()) / (1000 * 60 * 60);
      if (hoursSince < 24) {
        continue; // Skip if evaluated in last 24 hours
      }
    }
    
    await evaluateConversation(convId);
    evaluated++;
  }
  
  alert(`Evaluated ${evaluated} conversations!`);
  loadConversations(); // Reload to show updated badges
}

// Get priority badge HTML
function getPriorityBadge(priority, score) {
  const badges = {
    'critical': `<span class="priority-badge critical">🚨 Critical (${score}/10)</span>`,
    'high': `<span class="priority-badge high">⚠️ High (${score}/10)</span>`,
    'medium': `<span class="priority-badge medium">ℹ️ Medium (${score}/10)</span>`,
    'low': `<span class="priority-badge low">✅ Good (${score}/10)</span>`
  };
  return badges[priority] || '';
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  loadConversations();
});
