// Admin Dashboard JavaScript
let currentPage = 1;
let totalPages = 1;
let currentConversationId = null;
let currentTurnNumber = null;
let conversationEvaluations = {}; // Cache for AI evaluations
let conversationFeedbacks = {}; // Cache for feedbacks
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
    
    // Load AI evaluations and feedbacks for each conversation
    const conversations = data.conversations;
    await Promise.all(conversations.map(async conv => {
      await loadEvaluation(conv.id);
      await loadFeedback(conv.id);
    }));
    
    // Calculate summary statistics
    let criticalCount = 0;
    let criticalHandled = 0;
    let needsReviewCount = 0;
    let reviewHandled = 0;
    let approvedCount = 0;
    let reviewedCount = 0;  // New: count all reviewed turns
    
    conversations.forEach(conv => {
      const eval = conversationEvaluations[conv.id];
      const feedbacks = conversationFeedbacks[conv.id] || [];
      
      if (eval) {
        // Count critical turns (not just critical conversations)
        if (eval.turn_evaluations) {
          eval.turn_evaluations.forEach(turnEval => {
            const turnFeedback = feedbacks.find(fb => fb.turn_number === turnEval.turn_number);
            const isHandled = turnFeedback?.reviewed || false;
            
            // Count reviewed turns (any turn with feedback)
            if (isHandled) {
              reviewedCount++;
            }
            
            if (turnEval.evaluation?.priority === 'critical') {
              criticalCount++;
              if (isHandled) criticalHandled++;
            }
            if (turnEval.evaluation?.needs_review) {
              needsReviewCount++;
              if (isHandled) reviewHandled++;
            }
            if (turnEval.evaluation && !turnEval.evaluation.needs_review && turnEval.evaluation.overall_score >= 7) {
              approvedCount++;
            }
          });
        }
      }
    });
    
    // Update summary banner
    updateSummaryBanner(criticalCount, criticalHandled, needsReviewCount, reviewHandled, approvedCount, reviewedCount, conversations.length);
    
    // Apply filters
    let filteredConversations = conversations;
    
    // Filter by stat card selection (if any)
    if (activeStatFilter) {
      filteredConversations = filteredConversations.filter(conv => {
        const eval = conversationEvaluations[conv.id];
        const feedbacks = conversationFeedbacks[conv.id] || [];
        if (!eval || !eval.turn_evaluations) return false;
        
        switch(activeStatFilter) {
          case 'critical':
            // Show conversations with UNHANDLED critical turns
            return eval.turn_evaluations.some(turnEval => {
              if (turnEval.evaluation?.priority !== 'critical') return false;
              const turnFeedback = feedbacks.find(fb => fb.turn_number === turnEval.turn_number);
              return !turnFeedback?.reviewed; // Only show if NOT reviewed
            });
          case 'needs_review':
            // Show conversations with UNHANDLED turns that need review
            return eval.turn_evaluations.some(turnEval => {
              if (!turnEval.evaluation?.needs_review) return false;
              const turnFeedback = feedbacks.find(fb => fb.turn_number === turnEval.turn_number);
              return !turnFeedback?.reviewed; // Only show if NOT reviewed
            });
          case 'approved':
            // Check if conversation has any approved turns
            return eval.turn_evaluations.some(turnEval => 
              turnEval.evaluation && !turnEval.evaluation.needs_review && turnEval.evaluation.overall_score >= 7
            );
          case 'reviewed':
            // Show conversations with reviewed turns
            return eval.turn_evaluations.some(turnEval => {
              const turnFeedback = feedbacks.find(fb => fb.turn_number === turnEval.turn_number);
              return turnFeedback?.reviewed;
            });
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
    alert('Errore caricamento conversazioni');
  }
}

// Update summary banner
function updateSummaryBanner(critical, criticalHandled, needsReview, reviewHandled, approved, reviewed, total) {
  const criticalUnhandled = critical - criticalHandled;
  const reviewUnhandled = needsReview - reviewHandled;
  
  const banner = document.getElementById('summary-banner');
  banner.innerHTML = `
    <div class="summary-stats">
      <div class="stat-card critical ${activeStatFilter === 'critical' ? 'active' : ''}" onclick="filterByStats('critical')" style="cursor: pointer;">
        <div class="stat-number">${criticalUnhandled}</div>
        <div class="stat-label">🔴 Critici da Gestire</div>
        <div class="stat-sublabel">${criticalHandled} gestiti / ${critical} totali</div>
      </div>
      <div class="stat-card warning ${activeStatFilter === 'needs_review' ? 'active' : ''}" onclick="filterByStats('needs_review')" style="cursor: pointer;">
        <div class="stat-number">${reviewUnhandled}</div>
        <div class="stat-label">⚠️ Da Revisionare</div>
        <div class="stat-sublabel">${reviewHandled} gestiti / ${needsReview} totali</div>
      </div>
      <div class="stat-card reviewed ${activeStatFilter === 'reviewed' ? 'active' : ''}" onclick="filterByStats('reviewed')" style="cursor: pointer;">
        <div class="stat-number">${reviewed}</div>
        <div class="stat-label">📝 Risposte Revisionate</div>
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
    ${criticalUnhandled > 0 || reviewUnhandled > 0 ? `
      <div class="attention-message">
        👁️ <strong>${criticalUnhandled + reviewUnhandled} dialoghi richiedono la tua attenzione</strong>
        ${criticalUnhandled > 0 ? `<br>🔴 ${criticalUnhandled} critici non gestiti` : ''}
        ${reviewUnhandled > 0 ? `<br>⚠️ ${reviewUnhandled} da revisionare non gestiti` : ''}
      </div>
    ` : `
      <div class="attention-message success">
        🎉 Ottimo lavoro! Tutti i dialoghi critici e da revisionare sono stati gestiti!
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
          
          // Check if this turn has been reviewed
          const feedbacks = conversationFeedbacks[conv.id] || [];
          const turnFeedback = feedbacks.find(fb => fb.turn_number === turn.turn_number);
          const isReviewed = turnFeedback?.reviewed || false;
          
          return `
          <div class="dialogo ${turnEvalData?.needs_review ? 'revisione' : ''} ${isReviewed ? 'reviewed' : ''}" id="dialogo-${conv.id}-${turn.turn_number}">
            <div class="turn-header">
              <span>Dialogo ${turn.turn_number}</span>
              ${turnEvalData ? getPriorityBadge(turnEvalData.priority, turnEvalData.overall_score) : ''}
              ${isReviewed ? '<span class="reviewed-badge">✅ Gestito</span>' : ''}
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
        <h3>Conversazioni Totali</h3>
        <p class="metric-value">${data.conversations?.total_conversations || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Media Turni/Conv</h3>
        <p class="metric-value">${data.conversations?.avg_turns_per_conversation || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Feedback Totali</h3>
        <p class="metric-value">${data.feedback?.total_feedback || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Valutazione Media</h3>
        <p class="metric-value">${data.feedback?.avg_rating || 0} ⭐</p>
      </div>
      <div class="metric-card">
        <h3>Risposte Approvate</h3>
        <p class="metric-value">${data.approved_responses?.total_approved || 0}</p>
      </div>
      <div class="metric-card">
        <h3>Utilizzo Ricerca</h3>
        <p class="metric-value">${data.conversations?.search_usage?.conversations_with_search || 0}</p>
      </div>
    `;
  } catch (error) {
    console.error('Error loading analytics:', error);
  }
}

// Load approved responses
async function loadApprovedResponses() {
  try {
    showLoading('approved-content');
    
    const response = await fetch('/admin/api/approved-responses');
    if (!response.ok) throw new Error('Errore nel caricamento delle risposte approvate');
    
    const data = await response.json();
    const approvedResponses = data.approved_responses || [];
    
    const approvedContent = document.getElementById('approved-content');
    
    if (approvedResponses.length === 0) {
      approvedContent.innerHTML = '<div class="empty-state"><p>📚 Nessuna risposta approvata ancora.<br>Usa il pulsante <strong>⭐ Approva come Esempio</strong> per salvare le risposte migliori.</p></div>';
      return;
    }
    
    // Fetch conversation details for each approved response
    const conversationsCache = {};
    
    for (const approved of approvedResponses) {
      if (!conversationsCache[approved.conversation_id]) {
        try {
          const convResp = await fetch(`/admin/api/conversations?conversation_id=${approved.conversation_id}`);
          if (convResp.ok) {
            const convData = await convResp.json();
            if (convData.conversations && convData.conversations.length > 0) {
              conversationsCache[approved.conversation_id] = convData.conversations[0];
            }
          }
        } catch (e) {
          console.warn(`Could not load conversation ${approved.conversation_id}:`, e);
        }
      }
    }
    
    let html = '<div class="approved-responses-grid">';
    
    for (const approved of approvedResponses) {
      const conversation = conversationsCache[approved.conversation_id];
      const turn = conversation?.turns?.[approved.turn_number];
      
      const userQuery = turn?.user_message || 'N/A';
      const originalResponse = turn?.bot_response || 'N/A';
      const approvedResponse = approved.corrected_response || originalResponse;
      const rating = approved.rating || 5;
      const tags = approved.tags || [];
      const comment = approved.admin_comment || '';
      const timestamp = new Date(approved.timestamp).toLocaleString('it-IT');
      const adminUser = approved.admin_user || 'Admin';
      
      html += `
        <div class="approved-card">
          <div class="approved-header">
            <span class="approved-badge">⭐ Risposta Approvata</span>
            <span class="approved-date">${timestamp}</span>
          </div>
          
          <div class="approved-body">
            <div class="approved-section">
              <label>💬 Domanda Cliente:</label>
              <div class="approved-text">${escapeHtml(userQuery)}</div>
            </div>
            
            <div class="approved-section">
              <label>✅ Risposta Approvata:</label>
              <div class="approved-text approved-highlight">${escapeHtml(approvedResponse)}</div>
            </div>
            
            ${comment ? `
            <div class="approved-section">
              <label>📝 Note Admin:</label>
              <div class="approved-text">${escapeHtml(comment)}</div>
            </div>
            ` : ''}
            
            <div class="approved-footer">
              <div class="approved-meta">
                <span class="approved-rating">${'⭐'.repeat(rating)}</span>
                ${tags.length > 0 ? `<span class="approved-tags">${tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}</span>` : ''}
              </div>
              <div class="approved-link">
                <a href="#" onclick="viewApprovedConversation('${approved.conversation_id}', ${approved.turn_number}); return false;">
                  🔗 Visualizza Conversazione
                </a>
              </div>
            </div>
          </div>
        </div>
      `;
    }
    
    html += '</div>';
    approvedContent.innerHTML = html;
    
  } catch (error) {
    console.error('Error loading approved responses:', error);
    document.getElementById('approved-content').innerHTML = 
      '<div class="error-state"><p>❌ Errore nel caricamento delle risposte approvate.</p></div>';
  }
}

function viewApprovedConversation(conversationId, turnNumber) {
  // Switch to conversations tab
  const conversationsTab = document.querySelector('[data-tab="conversations"]');
  if (conversationsTab) conversationsTab.click();
  
  // Filter to show this conversation
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.value = conversationId;
    loadConversations();
    
    // After loading, scroll to the turn
    setTimeout(() => {
      const turnElement = document.getElementById(`dialogo-${conversationId}-${turnNumber}`);
      if (turnElement) {
        turnElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        turnElement.classList.add('highlight-turn');
        setTimeout(() => turnElement.classList.remove('highlight-turn'), 3000);
      }
    }, 1000);
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

// Load feedback for a conversation
async function loadFeedback(conversationId) {
  if (conversationFeedbacks[conversationId]) return;
  
  try {
    const response = await fetch(`/admin/api/feedback/${conversationId}`);
    if (response.ok) {
      const data = await response.json();
      conversationFeedbacks[conversationId] = data.feedbacks || [];
    } else {
      conversationFeedbacks[conversationId] = [];
    }
  } catch (error) {
    console.error(`Error loading feedback for ${conversationId}:`, error);
    conversationFeedbacks[conversationId] = [];
  }
}

// Load AI evaluation for a conversation
async function loadEvaluation(conversationId) {
  try {
    const response = await fetch(`/admin/api/evaluations/${conversationId}`);
    if (response.ok) {
      const evaluation = await response.json();
      conversationEvaluations[conversationId] = evaluation;
<<<<<<< HEAD
    } else if (response.status === 404) {
      // Evaluation not yet created for this conversation - this is normal
      // Silently continue without logging
      return;
    }
  } catch (error) {
    // Network error or other issue - silently continue
=======
    }
  } catch (error) {
    // Evaluation not found or error - silently continue
>>>>>>> 4152a758942a6fcbc7e1c9d22b4c9817b52223ad
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

// Helper functions
function showLoading(elementId) {
  const element = document.getElementById(elementId);
  if (element) {
    element.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="spinner"></div><p>Caricamento...</p></div>';
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  loadConversations();
});
