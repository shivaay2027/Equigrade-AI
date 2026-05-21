document.addEventListener('DOMContentLoaded', () => {
    // File Upload Handlers
    const setupUploadZone = (zoneId, inputId, nameId) => {
        const zone = document.getElementById(zoneId);
        const input = document.getElementById(inputId);
        const nameDisp = document.getElementById(nameId);

        zone.addEventListener('click', () => input.click());

        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });

        zone.addEventListener('dragleave', () => {
            zone.classList.remove('dragover');
        });

        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                nameDisp.textContent = input.files[0].name;
                nameDisp.style.color = '#38bdf8';
            }
        });

        input.addEventListener('change', () => {
            if (input.files.length) {
                nameDisp.textContent = input.files[0].name;
                nameDisp.style.color = '#38bdf8';
            }
        });
    };

    setupUploadZone('qp-zone', 'qp_file', 'qp-name');
    setupUploadZone('as-zone', 'as_file', 'as-name');

    // Form Submission
    const form = document.getElementById('eval-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('span');
    const btnLoader = document.getElementById('btn-loader');
    const statusText = document.getElementById('status-text');
    
    const inputSection = document.getElementById('input-section');
    const resultsSection = document.getElementById('results-section');
    const evalsContainer = document.getElementById('evaluations-container');
    const newEvalBtn = document.getElementById('new-eval-btn');

    newEvalBtn.addEventListener('click', () => {
        resultsSection.classList.add('hidden');
        inputSection.classList.remove('hidden');
        evalsContainer.innerHTML = '';
        form.reset();
        document.getElementById('qp-name').textContent = 'PDF or Image';
        document.getElementById('qp-name').style.color = '';
        document.getElementById('as-name').textContent = 'PDF or Image';
        document.getElementById('as-name').style.color = '';
        statusText.textContent = '';
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(form);
        
        if (!formData.get('as_file').name) {
            statusText.textContent = "Error: Answer Sheet is required.";
            statusText.style.color = "var(--error)";
            return;
        }

        // Loading State
        submitBtn.disabled = true;
        btnText.textContent = "Processing with AI...";
        btnLoader.style.display = "block";
        statusText.textContent = "Extracting files and analyzing against scheme. This may take a minute...";
        statusText.style.color = "var(--accent)";

        try {
            const response = await fetch('/api/evaluate', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Unknown error occurred");
            }

            renderResults(data.evaluations);
            
            inputSection.classList.add('hidden');
            resultsSection.classList.remove('hidden');

        } catch (err) {
            statusText.textContent = "Error: " + err.message;
            statusText.style.color = "var(--error)";
        } finally {
            submitBtn.disabled = false;
            btnText.textContent = "Evaluate Answer Sheet";
            btnLoader.style.display = "none";
        }
    });

    function renderResults(evaluations) {
        evalsContainer.innerHTML = '';
        
        if (!evaluations || evaluations.length === 0) {
            evalsContainer.innerHTML = '<p>No evaluations returned by AI.</p>';
            return;
        }

        evaluations.forEach((ev, i) => {
            const card = document.createElement('div');
            card.className = 'eval-card';
            card.style.animationDelay = `${i * 0.1}s`;

            let breakdownHtml = '';
            if (ev.marks_breakdown) {
                for (const [pt, mk] of Object.entries(ev.marks_breakdown)) {
                    breakdownHtml += `<li><span>${pt}</span> <strong>${mk}</strong></li>`;
                }
            }

            let missingHtml = '';
            if (ev.missing_points && ev.missing_points.length) {
                ev.missing_points.forEach(mp => {
                    missingHtml += `<li><span>${mp}</span></li>`;
                });
            } else {
                missingHtml = `<li style="color:#34d399; border:none; padding-left:0;">No missing points. Perfect answer!</li>`;
            }

            card.innerHTML = `
                <div class="eval-header">
                    <h3>Question: ${ev.question_number}</h3>
                    <div class="marks-badge">${ev.suggested_marks} / ${ev.total_marks} Marks</div>
                </div>
                <div class="eval-grid">
                    <div class="eval-left">
                        <div class="eval-section">
                            <h4>Extracted Answer</h4>
                            <p>${ev.extracted_answer || 'No answer detected.'}</p>
                        </div>
                        <div class="eval-section" style="margin-top: 1.5rem;">
                            <h4>AI Feedback</h4>
                            <p style="background: rgba(56, 189, 248, 0.1); border-left: 3px solid #38bdf8;">${ev.feedback || ''}</p>
                        </div>
                    </div>
                    <div class="eval-right">
                        <div class="eval-section">
                            <h4>Marks Breakdown</h4>
                            <ul class="breakdown-list">
                                ${breakdownHtml || '<li>No breakdown available</li>'}
                            </ul>
                        </div>
                        <div class="eval-section" style="margin-top: 1.5rem;">
                            <h4>Missing Points</h4>
                            <ul class="missing-list" ${(!ev.missing_points || ev.missing_points.length === 0) ? 'style="background: rgba(16, 185, 129, 0.1); border-left-color: #10b981;"' : ''}>
                                ${missingHtml}
                            </ul>
                        </div>
                    </div>
                </div>
            `;
            evalsContainer.appendChild(card);
        });
    }
});
