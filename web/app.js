document.addEventListener('DOMContentLoaded', () => {
    const runBtn = document.getElementById('btn-run-agent');
    const promptInput = document.getElementById('agent-prompt');
    const terminalOutput = document.getElementById('terminal-output');
    const agentState = document.getElementById('agent-state');

    const escapeHtml = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

    let lastMermaid = '';  // most recent diagram source, for the fullscreen view

    // Render Mermaid source into a container and make it zoom/pan-able. Shared by
    // the in-card preview and the fullscreen overlay.
    function renderMermaidInto(container, source, idPrefix) {
        const id = idPrefix + Date.now();
        container.innerHTML = `<div class="mermaid" id="${id}">${source}</div>`;
        // mermaid.run() is the v10+ API for dynamically injected content.
        setTimeout(async () => {
            try {
                await mermaid.run({ nodes: [document.getElementById(id)] });
                const svg = document.getElementById(id).querySelector('svg');
                if (svg && window.svgPanZoom) {
                    svg.setAttribute('width', '100%');
                    svg.setAttribute('height', '100%');
                    svg.style.maxWidth = 'none';
                    const pz = svgPanZoom(svg, {
                        zoomEnabled: true,
                        controlIconsEnabled: true,
                        fit: true,
                        center: true,
                        minZoom: 0.1,
                        maxZoom: 20,
                    });
                    // Re-fit once layout has fully settled (esp. inside the
                    // fullscreen overlay, where the container may size after init).
                    setTimeout(() => { pz.resize(); pz.fit(); pz.center(); }, 80);
                }
            } catch (err) {
                console.error('Mermaid error:', err);
                container.innerHTML = `<pre style="color:#aaa;font-size:0.75rem;padding:1rem;overflow:auto;max-height:100%">${escapeHtml(source)}</pre>`;
            }
        }, 50);
    }

    // Fullscreen diagram overlay: re-render the last diagram into the full viewport.
    const fsOverlay = document.getElementById('mermaid-fullscreen');
    function openMapFullscreen() {
        if (!lastMermaid) return;
        fsOverlay.style.display = 'flex';
        renderMermaidInto(document.getElementById('mermaid-fs-content'), lastMermaid, 'mermaid-fs-');
    }
    function closeMapFullscreen() {
        fsOverlay.style.display = 'none';
        document.getElementById('mermaid-fs-content').innerHTML = '';
    }
    document.getElementById('btn-expand-map').addEventListener('click', openMapFullscreen);
    document.getElementById('btn-close-map').addEventListener('click', closeMapFullscreen);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && fsOverlay.style.display === 'flex') closeMapFullscreen();
    });
    // Hide the Fullscreen button until a diagram exists.
    document.getElementById('btn-expand-map').style.visibility = 'hidden';

    // Render the actual code change as a compact hunk: trim the lines that
    // old/new share at the top and bottom, mark only what really changed, and
    // keep a few lines of context. Lets a human approve on what they SEE.
    function renderDiff(oldText, newText, filepath) {
        const fileEl = document.getElementById('vibe-file');
        const diffEl = document.getElementById('vibe-diff');
        if (!oldText && !newText) {
            fileEl.style.display = 'none';
            diffEl.style.display = 'none';
            return;
        }
        const CTX = 3;
        const o = (oldText || '').split('\n');
        const n = (newText || '').split('\n');
        let start = 0;
        while (start < o.length && start < n.length && o[start] === n[start]) start++;
        let endO = o.length, endN = n.length;
        while (endO > start && endN > start && o[endO - 1] === n[endN - 1]) { endO--; endN--; }

        const rows = [];
        for (let i = Math.max(0, start - CTX); i < start; i++) rows.push(['ctx', o[i]]);
        for (let i = start; i < endO; i++) rows.push(['del', o[i]]);
        for (let i = start; i < endN; i++) rows.push(['add', n[i]]);
        for (let i = endO; i < Math.min(o.length, endO + CTX); i++) rows.push(['ctx', o[i]]);

        diffEl.innerHTML = rows
            .map(([cls, text]) => `<span class="row ${cls}">${escapeHtml(text)}</span>`)
            .join('');
        fileEl.textContent = filepath || '';
        fileEl.style.display = filepath ? 'block' : 'none';
        diffEl.style.display = 'block';
    }

    runBtn.addEventListener('click', async () => {
        const prompt = promptInput.value.trim();
        if (!prompt) return;

        // Reset UI
        terminalOutput.textContent = '';
        agentState.textContent = 'Running...';
        runBtn.disabled = true;

        try {
            // Trigger the run
            const response = await fetch('/api/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt })
            });

            if (!response.body) throw new Error('ReadableStream not supported in this browser.');

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (!dataStr) continue;
                        try {
                            const data = JSON.parse(dataStr);

                            if (data.text) {
                                terminalOutput.textContent += data.text;
                                terminalOutput.scrollTop = terminalOutput.scrollHeight;
                            }

                            if (data.mermaid) {
                                lastMermaid = data.mermaid;
                                renderMermaidInto(document.getElementById('mermaid-container'), data.mermaid, 'mermaid-');
                                document.getElementById('btn-expand-map').style.visibility = 'visible';
                            }

                            if (data.status === 'complete') {
                                agentState.textContent = 'Awaiting Orders';
                                runBtn.disabled = false;
                            }

                            if (data.approval_required) {
                                agentState.textContent = 'Awaiting Approval';
                                document.getElementById('vibe-summary').textContent = data.proposed_solution || '';
                                renderDiff(data.old_text, data.new_text, data.filepath);
                                document.getElementById('approval-buttons').style.display = 'block';
                                document.querySelector('.vibe-diff-card').classList.add('awaiting');
                                runBtn.disabled = false;
                            }

                            if (data.error) {
                                terminalOutput.textContent += `\n\nERROR: ${data.error}`;
                                agentState.textContent = 'Error';
                                runBtn.disabled = false;
                            }
                        } catch(e) {
                            console.error("Failed to parse chunk:", dataStr);
                        }
                    }
                }
            }
        } catch (err) {
            console.error(err);
            terminalOutput.textContent += `\nFailed to start run: ${err.message}`;
            agentState.textContent = 'Error';
            runBtn.disabled = false;
        }
    });

    document.getElementById('btn-approve').addEventListener('click', async () => {
        document.getElementById('approval-buttons').style.display = 'none';
        document.querySelector('.vibe-diff-card').classList.remove('awaiting');
        agentState.textContent = 'Executing...';
        terminalOutput.textContent += '\n[User Approved] Executing edit and push...\n';

        const res = await fetch('/api/approve', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'approved') {
            terminalOutput.textContent += `[Edit Result] ${data.edit_result}\n`;
            if (data.push_result) terminalOutput.textContent += `[Push Result] ${data.push_result}\n`;
            if (data.cicd_status) {
                terminalOutput.textContent += `\n[CI/CD] ${data.cicd_status}\n`;
            }
            // Enable PR submission once the branch is pushed. Some repos only run
            // CI on the pull_request event, so we must allow opening the PR even
            // when no branch-level CI run exists yet (CI then runs on the PR).
            if (data.branch_name) {
                document.getElementById('btn-squash-push').disabled = false;
                document.getElementById('pr-title').textContent = `fix: ${document.getElementById('vibe-summary').textContent.slice(0, 60)}`;
                document.getElementById('dco-status').textContent = 'Signed-off \u2705';
            }
            if (data.ci_passed) {
                agentState.textContent = 'CI/CD Passed \u2705';
            } else if (data.branch_name) {
                agentState.textContent = data.cicd_status
                    ? 'CI/CD Failed \u274c'
                    : 'Branch Pushed \u2713 \u2014 open PR to run CI';
            }
        } else {
            terminalOutput.textContent += `[Error] ${data.message}\n`;
            agentState.textContent = 'Error';
        }
        runBtn.disabled = false;
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    });

    document.getElementById('btn-reject').addEventListener('click', async () => {
        document.getElementById('approval-buttons').style.display = 'none';
        document.querySelector('.vibe-diff-card').classList.remove('awaiting');
        document.getElementById('vibe-file').style.display = 'none';
        document.getElementById('vibe-diff').style.display = 'none';
        await fetch('/api/reject', { method: 'POST' });
        terminalOutput.textContent += '\n[User Rejected] Edit cancelled.\n';
        agentState.textContent = 'Awaiting Orders';
        runBtn.disabled = false;
    });

    document.getElementById('btn-new-task').addEventListener('click', async () => {
        await fetch('/api/reset', { method: 'POST' });
        terminalOutput.textContent = '';
        document.getElementById('vibe-summary').textContent = 'No changes staged.';
        document.getElementById('approval-buttons').style.display = 'none';
        document.querySelector('.vibe-diff-card').classList.remove('awaiting');
        document.getElementById('vibe-file').style.display = 'none';
        document.getElementById('vibe-diff').style.display = 'none';
        document.getElementById('btn-squash-push').disabled = true;
        document.getElementById('pr-title').textContent = '-';
        document.getElementById('dco-status').textContent = 'Unsigned';
        agentState.textContent = 'Awaiting Orders';
        runBtn.disabled = false;
    });

    document.getElementById('btn-squash-push').addEventListener('click', async () => {
        agentState.textContent = 'Submitting PR...';
        document.getElementById('btn-squash-push').disabled = true;

        const res = await fetch('/api/submit-pr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();

        if (data.status === 'submitted') {
            terminalOutput.textContent += `\n[PR] ${data.result}\n`;
            if (data.cicd_status) {
                terminalOutput.textContent += `\n[CI/CD] ${data.cicd_status}\n`;
            }
            agentState.textContent = data.ci_passed
                ? 'PR Submitted — CI Passed ✅'
                : 'PR Submitted ✅';
            // Extract and display PR URL
            const urlMatch = data.result.match(/https:\/\/github\.com\/\S+/);
            if (urlMatch) {
                document.getElementById('pr-title').innerHTML =
                    `<a href="${urlMatch[0]}" target="_blank" style="color:#7dd3fc">${urlMatch[0]}</a>`;
            }
        } else {
            terminalOutput.textContent += `\n[PR Error] ${data.result || data.message}\n`;
            agentState.textContent = 'PR Failed';
            document.getElementById('btn-squash-push').disabled = false;
        }
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    });

    document.getElementById('btn-request-changes').addEventListener('click', () => {
        const existing = document.getElementById('request-changes-input');
        if (existing) { existing.remove(); return; }

        const container = document.querySelector('.pr-compliance-card .glass-container');
        const area = document.createElement('div');
        area.id = 'request-changes-input';
        area.style.cssText = 'margin-top:1rem; display:flex; flex-direction:column; gap:0.5rem';
        area.innerHTML = `
            <textarea id="changes-text" rows="3" placeholder="Describe what needs to change..."
                style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.15);
                       color:white; padding:0.5rem; border-radius:4px; resize:vertical; font-family:inherit"></textarea>
            <button id="btn-send-changes" class="btn primary" style="align-self:flex-end">Send to Agent</button>`;
        container.appendChild(area);

        document.getElementById('btn-send-changes').addEventListener('click', async () => {
            const feedback = document.getElementById('changes-text').value.trim();
            if (!feedback) return;
            area.remove();
            promptInput.value = feedback;
            runBtn.click();
        });
    });
});
