// Admin Dashboard JavaScript
let currentPage = 1;
let totalPages = 1;
let currentConversationId = null;
let currentTurnNumber = null;
let conversationEvaluations = {}; // Cache for AI evaluations
let activeStatFilter = null; // Track active stat filter: 'critical', 'needs_review', 'approved', 'all', or null

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
    page_size: 50  // Increased to show more when filtering
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
    
    // Calculate summary statistics
    let criticalCount = 0;
    let needsReviewCount = 0;
    let approvedCount = 0;
    
    conversations.forEach(conv => {
      const eval = conversationEvaluations[conv.id];
      if (eval) {
        if (eval.priority === 'critical') criticalCount++;
        if (eval.needs_review) needsReviewCount++;
        if (!eval.needs_review && eval.overall_score >= 7) approvedCount++;
      }
    });
    
    // Update summary banner
    updateSummaryBanner(criticalCount, needsReviewCount, approvedCount, conversations.length);
    
    // Apply filters
    let filteredConversations = conversations;
    
    // Filter by stat card selection (if any)
    if (activeStatFilter) {
      filteredConversations = filteredConversations.filter(conv => {
        const eval = conversationEvaluations[conv.id];
        if (!eval) return false;
        
        switch(activeStatFilter) {
          case 'critical':
            return eval.priority === 'critical';
          case 'needs_review':
            return eval.needs_review;
          case 'approved':
            return !eval.needs_review && eval.overall_score >= 7;
          case 'all':
            return true;
          default:
            return true;
        }
      });
    } else if (needsReview) {
      // Fallback to checkbox filter if no stat filter is active
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

// Update summary banner
function updateSummaryBanner(critical, needsReview, approved, total) {
  const banner = document.getElementById('summary-banner');
  banner.innerHTML = `
    <div class="summary-stats">
      <div class="stat-card critical ${activeStatFilter === 'critical' ? 'active' : ''}" onclick="filterByStats('critical')" style="cursor: pointer;">
        <div class="stat-number">${critical}</div>
        <div class="stat-label">🔴 Critici</div>
      </div>
      <div class="stat-card warning ${activeStatFilter === 'needs_review' ? 'active' : ''}" onclick="filterByStats('needs_review')" style="cursor: pointer;">
        <div class="stat-number">${needsReview}</div>
        <div class="stat-label">⚠️ Da Revisionare</div>
      </div>
      <div class="stat-card success ${activeStatFilter === 'approved' ? 'active' : ''}" onclick="filterByStats('approved')" style="cursor: pointer;">
        <div class="stat-number">${approved}</div>
        <div class="stat-label">✅ Risposte Approvate</div>
      </div>
      <div class="stat-card info ${activeStatFilter === 'all' ? 'active' : ''}" onclick="filterByStats('all')" style="cursor: pointer;">
        <div class="stat-number">${total}</div>
        <div class="stat-label">📊 Conversazioni Totali</div>
      </div>
    </div>
    ${needsReview > 0 ? `
      <div class="attention-message">
        👁️ <strong>${needsReview} conversazione${needsReview > 1 ? 'i' : ''} necessita${needsReview === 1 ? '' : 'no'} la tua attenzione</strong> (su un totale di ${total})
      </div>
    ` : `
      <div class="attention-message success">
        🎉 Tutte le conversazioni sono a posto! Nessuna revisione immediata necessaria.
      </div>
    `}
  `;
}

// Display conversations
function displayConversations(conversations) {
  const container = document.getElementById('conversations-list');
  
  if (conversations.length === 0) {
    container.innerHTML = '<p class="empty">Nessuna conversazione trovata</p>';
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
        <span>💬 ${conv.total_turns} dialoghi</span>
        <span>⏱️ ${conv.duration_seconds}s</span>
        ${evaluation ? `<span>🤖 Punteggio AI: ${evaluation.overall_score}/10</span>` : ''}
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
        <p><strong>Canale:</strong> ${conv.channel}</p>
        <p><strong>Data:</strong> ${new Date(conv.timestamp).toLocaleString('it-IT')}</p>
        <p><strong>Dialoghi:</strong> ${conv.turns.length}</p>
        ${conv.pii_detected_types && conv.pii_detected_types.length > 0 ? 
          `<p><strong>PII Rilevati:</strong> ${conv.pii_detected_types.join(', ')}</p>` : ''}
        ${evaluation ? `
          <div class="ai-evaluation-summary">
            <p><strong>🤖 Valutazione AI:</strong></p>
            <p>Punteggio Complessivo: <strong>${evaluation.overall_score}/10</strong></p>
            <p>Priorità: ${getPriorityBadge(evaluation.priority, evaluation.overall_score)}</p>
            <p>Necessita Revisione: ${evaluation.needs_review ? '✅ Sì' : '❌ No'}</p>
            ${evaluation.critical_turns && evaluation.critical_turns.length > 0 ? 
              `<p>Turni Critici: ${evaluation.critical_turns.join(', ')}</p>` : ''}
          </div>
        ` : `
          <button onclick="evaluateSingleConversation('${conv.id}')" class="eval-btn">
            🤖 Valuta con AI
          </button>
        `}
      </div>
      
      <div class="turns">
        ${conv.turns.map(turn => {
          const turnEval = evaluation?.turn_evaluations?.find(e => e.turn_number === turn.turn_number);
          const turnEvalData = turnEval?.evaluation;
          
          return `
          <div class="dialogo ${turnEvalData?.needs_review ? 'revisione' : ''}" id="dialogo-${conv.id}-${turn.turn_number}">
            <div class="turn-header">
              <span>Dialogo ${turn.turn_number}</span>
              ${turnEvalData ? getPriorityBadge(turnEvalData.priority, turnEvalData.overall_score) : ''}
              <button onclick="toggleInlineFeedback('${conv.id}', ${turn.turn_number})" class="feedback-btn">
                💬 Feedback
              </button>
            </div>
            ${turnEvalData ? `
              <div class="ai-turn-evaluation">
                <p><strong>🤖 Analisi AI:</strong> Punteggio ${turnEvalData.overall_score}/10</p>
                ${turnEvalData.evaluation_summary ? `<p><em>${turnEvalData.evaluation_summary}</em></p>` : ''}
                ${turnEvalData.issues && turnEvalData.issues.length > 0 ? `
                  <p><strong>Problemi:</strong> ${turnEvalData.issues.join(', ')}</p>
                ` : ''}
                ${turnEvalData.strengths && turnEvalData.strengths.length > 0 ? `
                  <p><strong>Punti di Forza:</strong> ${turnEvalData.strengths.join(', ')}</p>
                ` : ''}
                <details>
                  <summary>Punteggi per Categoria</summary>
                  <ul>
                    ${Object.entries(turnEvalData.categories || {}).map(([cat, score]) => 
                      `<li>${cat}: ${score}/10</li>`
                    ).join('')}
                  </ul>
                </details>
              </div>
            ` : ''}
            <div class="message user-message">
              <strong>Utente:</strong> ${turn.user_message}
            </div>
            <div class="message bot-message">
              <strong>Bot:</strong> ${turn.bot_response}
            </div>
            ${turn.search_used ? `
              <div class="search-info">
                🔍 Ricerca utilizzata: "${turn.search_query || 'N/A'}"
              </div>
            ` : ''}
          </div>
        `}).join('')}
      </div>
    `;
    
    modal.style.display = 'block';
  } catch (error) {
    console.error('Errore caricamento conversazione:', error);
    alert('Errore durante il caricamento dei dettagli della conversazione');
  }
}

// Evaluate a single conversation and reload view
async function evaluateSingleConversation(conversationId) {
  const evaluation = await evaluateConversation(conversationId);
  if (evaluation) {
    // Check if there was an error in the evaluation
    if (evaluation.error) {
      alert(`⚠️ Valutazione completata con problemi:\n\n${evaluation.error}\n\nPunteggio: ${evaluation.overall_score}/10`);
    } else {
      alert('✅ Conversazione valutata con successo!');
    }
    viewConversation(conversationId); // Reload the view
  } else {
    alert('❌ Errore: Impossibile valutare la conversazione. Controlla i log del server per i dettagli.');
  }
}

// Close modal
function closeModal() {
  document.getElementById('conversation-modal').style.display = 'none';
}

// Toggle inline feedback form with AI pre-fill
async function toggleInlineFeedback(conversationId, turnNumber) {
  const turnDiv = document.getElementById(`dialogo-${conversationId}-${turnNumber}`);
  if (!turnDiv) {
    console.error(`Turn div not found: dialogo-${conversationId}-${turnNumber}`);
    return;
  }
  const existingForm = turnDiv.querySelector('.inline-feedback-form');
  
  // If form already exists, remove it
  if (existingForm) {
    existingForm.remove();
    return;
  }
  
  // Close any other open feedback forms
  document.querySelectorAll('.inline-feedback-form').forEach(form => form.remove());
  
  // Clone the template
  const template = document.getElementById('feedback-form-template');
  const formClone = template.content.cloneNode(true);
  const formDiv = formClone.querySelector('.inline-feedback-form');
  
  // Store conversation and turn data
  formDiv.dataset.conversationId = conversationId;
  formDiv.dataset.turnNumber = turnNumber;
  
  // Append to turn
  turnDiv.appendChild(formClone);
  
  // Pre-fill with AI suggestions
  await prefillAISuggestions(formDiv, conversationId, turnNumber);
  
  // Scroll into view
  formDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Pre-fill feedback form with AI suggestions
async function prefillAISuggestions(formDiv, conversationId, turnNumber) {
  const loadingMsg = document.createElement('div');
  loadingMsg.className = 'ai-loading';
  loadingMsg.innerHTML = '🤖 AI sta preparando suggerimenti...';
  formDiv.insertBefore(loadingMsg, formDiv.firstChild);
  
  try {
    // Get the conversation evaluation
    const evaluation = conversationEvaluations[conversationId];
    const turnEval = evaluation?.turn_evaluations?.find(e => e.turn_number === turnNumber);
    const turnEvalData = turnEval?.evaluation;
    
    if (turnEvalData) {
      // Set rating based on AI score (convert 0-10 to 1-5)
      const suggestedRating = Math.max(1, Math.min(5, Math.round(turnEvalData.overall_score / 2)));
      setInlineRating(formDiv.querySelector('.rating button:nth-child(' + suggestedRating + ')'), suggestedRating);
      
      // Pre-check relevant tags based on AI analysis
      const tagsToCheck = [];
      
      if (turnEvalData.overall_score >= 8) {
        tagsToCheck.push('excellent', 'helpful', 'accurate');
      } else if (turnEvalData.overall_score >= 6) {
        tagsToCheck.push('helpful', 'accurate');
      }
      
      if (turnEvalData.issues && turnEvalData.issues.length > 0) {
        if (turnEvalData.issues.some(i => i.toLowerCase().includes('context'))) {
          tagsToCheck.push('context_lost');
        }
        if (turnEvalData.issues.some(i => i.toLowerCase().includes('incorrect') || i.toLowerCase().includes('wrong'))) {
          tagsToCheck.push('wrong_info');
        }
        if (turnEvalData.issues.some(i => i.toLowerCase().includes('tone') || i.toLowerCase().includes('tono'))) {
          tagsToCheck.push('tone_issue');
        }
      }
      
      // Check the tags
      formDiv.querySelectorAll('.tags input[type="checkbox"]').forEach(cb => {
        if (tagsToCheck.includes(cb.value)) {
          cb.checked = true;
        }
      });
      
      // Pre-fill admin comment with AI analysis in Italian
      let adminComment = '🤖 Suggerimento AI:\n\n';
      
      if (turnEvalData.evaluation_summary) {
        adminComment += `${turnEvalData.evaluation_summary}\n\n`;
      }
      
      if (turnEvalData.issues && turnEvalData.issues.length > 0) {
        adminComment += `Problemi identificati:\n${turnEvalData.issues.map(i => '• ' + i).join('\n')}\n\n`;
      }
      
      if (turnEvalData.strengths && turnEvalData.strengths.length > 0) {
        adminComment += `Punti di forza:\n${turnEvalData.strengths.map(s => '• ' + s).join('\n')}\n\n`;
      }
      
      adminComment += '---\nModifica o aggiungi le tue osservazioni sopra.';
      
      formDiv.querySelector('.admin-comment').value = adminComment;
      
      // If there are issues and score is low, suggest a corrected response
      if (turnEvalData.overall_score < 6 && turnEvalData.suggested_improvement) {
        formDiv.querySelector('.corrected-response').value = turnEvalData.suggested_improvement;
      }
      
      loadingMsg.innerHTML = '✅ Suggerimenti AI caricati! Puoi modificarli prima di inviare.';
      loadingMsg.style.background = '#d4edda';
      loadingMsg.style.color = '#155724';
      setTimeout(() => loadingMsg.remove(), 3000);
    } else {
      loadingMsg.innerHTML = 'ℹ️ Nessuna valutazione AI disponibile. Compila manualmente.';
      loadingMsg.style.background = '#fff3cd';
      loadingMsg.style.color = '#856404';
      setTimeout(() => loadingMsg.remove(), 3000);
    }
  } catch (error) {
    console.error('Error pre-filling AI suggestions:', error);
    loadingMsg.innerHTML = '⚠️ Errore nel caricamento dei suggerimenti AI.';
    loadingMsg.style.background = '#f8d7da';
    loadingMsg.style.color = '#721c24';
    setTimeout(() => loadingMsg.remove(), 3000);
  }
}

// Close inline feedback
function closeInlineFeedback(button) {
  const form = button.closest('.inline-feedback-form');
  form.remove();
}

// Set rating for inline form
function setInlineRating(button, rating) {
  const form = button.closest('.inline-feedback-form');
  form.querySelector('.selected-rating').value = rating;
  form.querySelectorAll('.rating button').forEach((btn, idx) => {
    btn.style.opacity = idx < rating ? '1' : '0.3';
  });
}

// Submit inline feedback
async function submitInlineFeedback(button) {
  const form = button.closest('.inline-feedback-form');
  const conversationId = form.dataset.conversationId;
  const turnNumber = parseInt(form.dataset.turnNumber);
  
  const rating = parseInt(form.querySelector('.selected-rating').value);
  const comment = form.querySelector('.admin-comment').value;
  const corrected = form.querySelector('.corrected-response').value;
  
  const tags = [];
  form.querySelectorAll('.tags input:checked').forEach(cb => {
    tags.push(cb.value);
  });
  
  try {
    button.disabled = true;
    button.textContent = '⏳ Invio...';
    
    const response = await fetch(`/admin/api/feedback/${conversationId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        conversation_id: conversationId,
        turn_number: turnNumber,
        rating,
        tags,
        admin_comment: comment,
        corrected_response: corrected
      })
    });
    
    if (response.ok) {
      alert('✅ Feedback inviato con successo!');
      form.remove();
      loadConversations(); // Refresh list
    } else {
      alert('❌ Errore durante l\'invio del feedback');
      button.disabled = false;
      button.textContent = '💾 Invia Feedback';
    }
  } catch (error) {
    console.error('Error submitting feedback:', error);
    alert('❌ Errore durante l\'invio del feedback');
    button.disabled = false;
    button.textContent = '💾 Invia Feedback';
  }
}

// Approve inline response for learning
async function approveInlineResponse(button) {
  const form = button.closest('.inline-feedback-form');
  const conversationId = form.dataset.conversationId;
  const turnNumber = parseInt(form.dataset.turnNumber);
  
  try {
    button.disabled = true;
    button.textContent = '⏳ Approvazione in corso...';
    
    const response = await fetch(`/admin/api/approve/${conversationId}/${turnNumber}`, {
      method: 'POST'
    });
    
    if (response.ok) {
      alert('✅ Risposta approvata per l\'apprendimento del bot!');
      form.remove();
      loadConversations();
    } else {
      alert('❌ Errore durante l\'approvazione della risposta');
      button.disabled = false;
      button.textContent = '✅ Approva per Apprendimento';
    }
  } catch (error) {
    console.error('Errore durante l\'approvazione della risposta:', error);
    alert('❌ Errore durante l\'approvazione della risposta');
    button.disabled = false;
    button.textContent = '✅ Approva per Apprendimento';
  }
}

// Approve response for learning
async function approveResponse() {
  if (!confirm('Approva questa risposta per l\'apprendimento del bot?')) return;
  
  try {
    const response = await fetch(`/admin/api/approve/${currentConversationId}/${currentTurnNumber}`, {
      method: 'POST'
    });
    
    if (response.ok) {
      alert('Risposta approvata e indicizzata per l\'apprendimento!');
      closeFeedbackModal();
    } else {
      alert('Errore durante l\'approvazione della risposta');
    }
  } catch (error) {
    console.error('Errore durante l\'approvazione della risposta:', error);
    alert('Errore durante l\'approvazione della risposta');
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
        alert(`⚠️ Errore durante la valutazione:\n\n${errorData.error}`);
      }
    }
  } catch (error) {
    console.error(`Errore durante la valutazione della conversazione ${conversationId}:`, error);
  }
  return null;
}

// Evaluate all visible conversations
async function evaluateAllConversations() {
  if (!confirm('Valutare tutte le conversazioni con l\'IA? Questo potrebbe richiedere qualche istante.')) {
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
  
  alert(`Valutate ${evaluated} conversazioni!`);
  loadConversations(); // Reload to show updated badges
}

// Get priority badge HTML
function getPriorityBadge(priority, score) {
  const badges = {
    'critical': `<span class="priority-badge critical">🚨 Critico (${score}/10)</span>`,
    'high': `<span class="priority-badge high">⚠️ Alto (${score}/10)</span>`,
    'medium': `<span class="priority-badge medium">ℹ️ Medio (${score}/10)</span>`,
    'low': `<span class="priority-badge low">✅ Buono (${score}/10)</span>`
  };
  return badges[priority] || '';
}

// Filter by stats card
function filterByStats(filterType) {
  // Toggle filter: if clicking the same filter, deactivate it
  if (activeStatFilter === filterType) {
    activeStatFilter = null;
    // Uncheck the needs-review checkbox if it's active
    const checkbox = document.getElementById('needs-review-filter');
    if (checkbox && filterType !== 'all') {
      checkbox.checked = false;
    }
  } else {
    activeStatFilter = filterType;
    // Sync with checkbox when selecting 'needs_review'
    const checkbox = document.getElementById('needs-review-filter');
    if (checkbox && filterType === 'needs_review') {
      checkbox.checked = true;
    } else if (checkbox) {
      checkbox.checked = false;
    }
  }
  
  // Reset to page 1 and reload
  currentPage = 1;
  loadConversations();
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  loadConversations();
});
