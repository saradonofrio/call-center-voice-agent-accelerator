// Admin Dashboard JavaScript
let currentPage = 1;
let totalPages = 1;
let currentConversationId = null;
let currentTurnNumber = null;

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
    
    totalPages = data.total_pages;
    displayConversations(data.conversations);
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
  
  container.innerHTML = conversations.map(conv => `
    <div class="conversation-card" onclick="viewConversation('${conv.id}')">
      <div class="conv-header">
        <span class="conv-id">${conv.id}</span>
        <span class="conv-channel ${conv.channel}">${conv.channel}</span>
        ${conv.pii_detected ? '<span class="pii-badge">🔒 PII</span>' : ''}
      </div>
      <div class="conv-meta">
        <span>📅 ${new Date(conv.timestamp).toLocaleString('it-IT')}</span>
        <span>💬 ${conv.total_turns} turns</span>
        <span>⏱️ ${conv.duration_seconds}s</span>
      </div>
    </div>
  `).join('');
}

// View conversation detail
async function viewConversation(conversationId) {
  try {
    const response = await fetch(`/admin/api/conversations/${conversationId}`);
    const conv = await response.json();
    
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
      </div>
      
      <div class="turns">
        ${conv.turns.map(turn => `
          <div class="turn">
            <div class="turn-header">
              <span>Turn ${turn.turn_number}</span>
              <button onclick="openFeedbackModal('${conv.id}', ${turn.turn_number})" class="feedback-btn">
                💬 Feedback
              </button>
            </div>
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
        `).join('')}
      </div>
    `;
    
    modal.style.display = 'block';
  } catch (error) {
    console.error('Error loading conversation:', error);
    alert('Error loading conversation details');
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

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  loadConversations();
});
