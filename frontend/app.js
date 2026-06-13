// AutoIntern JavaScript Controller - Manage state, API calls, and DOM updates

const API_BASE = window.location.origin === "file://" || window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
    ? "http://localhost:8000/api" 
    : (window.location.origin.includes("vercel.app") || window.location.origin.includes("github.io") || window.location.origin.includes("netlify.app")
        ? "https://your-backend-api-url.onrender.com/api" // UPDATE this with your Render/Railway backend URL if hosting separately
        : window.location.origin + "/api");
const DEFAULT_EMAIL = "student.test@example.edu";

// App State
let state = {
    activeTab: "profile",
    userProfile: null,
    jobs: [],
    applications: [],
    selectedJob: null,
    scoringMode: "keyword", // 'keyword' or 'ai'
    filters: {
        search: "",
        portal: ""
    }
};

// DOM Elements
const elements = {
    navItems: document.querySelectorAll(".nav-item"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    tabTitle: document.getElementById("current-tab-title"),
    tabDesc: document.getElementById("current-tab-desc"),
    
    // Resume Profile elements
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    progressContainer: document.getElementById("progress-container"),
    uploadFilename: document.getElementById("upload-filename"),
    uploadPercent: document.getElementById("upload-percent"),
    uploadProgress: document.getElementById("upload-progress"),
    uploadStatus: document.getElementById("upload-status"),
    profileEmpty: document.getElementById("profile-empty"),
    profileDataView: document.getElementById("profile-data-view"),
    profileName: document.getElementById("profile-name"),
    profileEmail: document.getElementById("profile-email"),
    profileSkills: document.getElementById("profile-skills"),
    profileTimeline: document.getElementById("profile-timeline"),
    resumeVersion: document.getElementById("resume-version"),
    
    // Job Feed elements
    jobSearch: document.getElementById("job-search"),
    portalFilter: document.getElementById("portal-filter"),
    btnScrape: document.getElementById("btn-scrape"),
    resultsCount: document.getElementById("results-count"),
    scrapeStatusBanner: document.getElementById("scrape-status-banner"),
    scrapeStatusText: document.getElementById("scrape-status-text"),
    jobsList: document.getElementById("jobs-list"),
    
    // Modal elements
    modalContainer: document.getElementById("modal-container"),
    modalClose: document.getElementById("modal-close"),
    modalPortal: document.getElementById("modal-portal"),
    modalTitle: document.getElementById("modal-title"),
    modalCompany: document.getElementById("modal-company"),
    modalLocation: document.getElementById("modal-location"),
    modalStipend: document.getElementById("modal-stipend"),
    modalScoreVal: document.getElementById("modal-score-val"),
    modalCircleScore: document.getElementById("modal-circle-score"),
    modalJDText: document.getElementById("modal-jd-text"),
    copilotTabs: document.querySelectorAll(".copilot-tab"),
    subtabPanes: document.querySelectorAll(".subtab-pane"),
    modeKeyword: document.getElementById("mode-keyword"),
    modeAI: document.getElementById("mode-ai"),
    analysisReason: document.getElementById("analysis-reason"),
    analysisMatchingSkills: document.getElementById("analysis-matching-skills"),
    analysisMissingSkills: document.getElementById("analysis-missing-skills"),
    analysisRec: document.getElementById("analysis-rec"),
    recommendationBlock: document.getElementById("recommendation-block"),
    
    // Tailor section
    btnRunTailoring: document.getElementById("btn-run-tailoring"),
    tailoringResultsView: document.getElementById("tailoring-results-view"),
    tailorLoadingState: document.getElementById("tailor-loading-state"),
    tailoredBulletsText: document.getElementById("tailored-bullets-text"),
    tailoredLetterText: document.getElementById("tailored-letter-text"),
    btnSaveDraft: document.getElementById("btn-save-draft"),
    btnOpenSendOutreach: document.getElementById("btn-open-send-outreach"),
    
    // Outreach Modal elements
    outreachModalContainer: document.getElementById("outreach-modal-container"),
    outreachModalClose: document.getElementById("outreach-modal-close"),
    outreachEmailInput: document.getElementById("outreach-email-input"),
    outreachSubjectInput: document.getElementById("outreach-subject-input"),
    btnConfirmSendOutreach: document.getElementById("btn-confirm-send-outreach"),

    // Kanban Board Elements
    kanbanDraft: document.getElementById("kanban-draft"),
    kanbanApplied: document.getElementById("kanban-applied"),
    kanbanSeen: document.getElementById("kanban-seen"),
    kanbanReplied: document.getElementById("kanban-replied"),
    kanbanInterview: document.getElementById("kanban-interview"),
    badgeDraft: document.getElementById("badge-draft"),
    badgeApplied: document.getElementById("badge-applied"),
    badgeSeen: document.getElementById("badge-seen"),
    badgeReplied: document.getElementById("badge-replied"),
    badgeInterview: document.getElementById("badge-interview"),
    webhookEmail: document.getElementById("webhook-email"),
    btnSimulateWebhook: document.getElementById("btn-simulate-webhook"),
    
    // General
    toast: document.getElementById("toast")
};

// Start
document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initFileUpload();
    initJobFeed();
    initModal();
    initOutreachModal();
    initKanbanView();
    loadProfileAndJobs();
});

// ── Navigation Manager ──
function initNavigation() {
    elements.navItems.forEach(item => {
        item.addEventListener("click", () => {
            const tabName = item.getAttribute("data-tab");
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    state.activeTab = tabName;
    
    // Update nav buttons
    elements.navItems.forEach(btn => {
        if (btn.getAttribute("data-tab") === tabName) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    // Update panes
    elements.tabPanes.forEach(pane => {
        if (pane.id === `tab-${tabName}`) {
            pane.classList.add("active");
        } else {
            pane.classList.remove("active");
        }
    });
    
    // Header Info Update
    if (tabName === "profile") {
        elements.tabTitle.textContent = "Resume Profile";
        elements.tabDesc.textContent = "Upload your resume to extract details and generate optimized job search queries.";
    } else if (tabName === "feed") {
        elements.tabTitle.textContent = "Internship Feed";
        elements.tabDesc.textContent = "Browse cached internships and view dynamic matching scores tailored to your profile.";
        fetchJobs(); // reload jobs whenever user clicks Feed tab
    } else if (tabName === "kanban") {
        elements.tabTitle.textContent = "Kanban Tracker";
        elements.tabDesc.textContent = "Track application drafts, direct email outreaches, recruiter opens, and replies.";
        fetchApplications();
    }
}

// ── File Upload Manager (Resume) ──
function initFileUpload() {
    const dropzone = elements.dropzone;
    
    dropzone.addEventListener("click", () => elements.fileInput.click());
    
    elements.fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleResumeUpload(e.target.files[0]);
        }
    });
    
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });
    
    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });
    
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            handleResumeUpload(e.dataTransfer.files[0]);
        }
    });
}

async function handleResumeUpload(file) {
    if (!file.name.endsWith(".pdf")) {
        showToast("Error: Please select a valid PDF file.", true);
        return;
    }
    
    // UI Progress State
    elements.dropzone.classList.add("hidden");
    elements.progressContainer.classList.remove("hidden");
    elements.uploadFilename.textContent = file.name;
    elements.uploadPercent.textContent = "15%";
    elements.uploadProgress.style.width = "15%";
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        elements.uploadPercent.textContent = "40%";
        elements.uploadProgress.style.width = "40%";
        
        const response = await fetch(`${API_BASE}/resume/upload`, {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to parse PDF resume.");
        }
        
        elements.uploadPercent.textContent = "90%";
        elements.uploadProgress.style.width = "90%";
        elements.uploadStatus.textContent = "Finalizing profile analysis...";
        
        const data = await response.json();
        
        setTimeout(() => {
            elements.progressContainer.classList.add("hidden");
            elements.dropzone.classList.remove("hidden");
            
            if (data.success && data.parsed_resume) {
                renderProfile(data.parsed_resume, data.version);
                showToast("Resume parsed and saved successfully!");
            }
        }, 800);
        
    } catch (e) {
        loggerError(e);
        elements.progressContainer.classList.add("hidden");
        elements.dropzone.classList.remove("hidden");
        showToast(e.message || "An error occurred during resume uploading.", true);
    }
}

// ── Profile Rendering ──
function renderProfile(parsedResume, version = null) {
    state.userProfile = parsedResume;
    
    elements.profileEmpty.classList.add("hidden");
    elements.profileDataView.classList.remove("hidden");
    
    if (version) {
        elements.resumeVersion.textContent = `v${version}`;
        elements.resumeVersion.classList.remove("hidden");
    } else {
        elements.resumeVersion.classList.add("hidden");
    }
    
    elements.profileName.textContent = parsedResume.name || "N/A";
    elements.profileEmail.innerHTML = `<i class="fa-regular fa-envelope"></i> ${parsedResume.email || "N/A"}`;
    
    // Skills
    elements.profileSkills.innerHTML = "";
    const skills = parsedResume.skills || [];
    if (skills.length > 0) {
        skills.forEach(skill => {
            const span = document.createElement("span");
            span.className = "skill-chip";
            span.textContent = skill;
            elements.profileSkills.appendChild(span);
        });
    } else {
        elements.profileSkills.innerHTML = "<p class='text-muted'>No skills extracted.</p>";
    }
    
    // Timeline (Experience & Projects combined)
    elements.profileTimeline.innerHTML = "";
    
    const experiences = parsedResume.experience || [];
    experiences.forEach(exp => {
        const item = document.createElement("div");
        item.className = "timeline-item";
        
        let bulletsHtml = "";
        if (exp.bullets && exp.bullets.length > 0) {
            bulletsHtml = `<ul class="timeline-bullets">` + 
                exp.bullets.map(b => `<li>${b}</li>`).join("") + 
                `</ul>`;
        }
        
        item.innerHTML = `
            <div class="timeline-header">
                <span class="timeline-title">${exp.role || "Intern"}</span>
                <span class="timeline-subtitle">${exp.company || "Company"}</span>
            </div>
            ${bulletsHtml}
        `;
        elements.profileTimeline.appendChild(item);
    });
    
    const projects = parsedResume.projects || [];
    projects.forEach(proj => {
        const item = document.createElement("div");
        item.className = "timeline-item";
        
        let bulletsHtml = "";
        if (proj.bullets && proj.bullets.length > 0) {
            bulletsHtml = `<ul class="timeline-bullets">` + 
                proj.bullets.map(b => `<li>${b}</li>`).join("") + 
                `</ul>`;
        }
        
        item.innerHTML = `
            <div class="timeline-header">
                <span class="timeline-title">${proj.title || "Project"}</span>
                <span class="timeline-subtitle">Independent Project</span>
            </div>
            <p class="timeline-desc" style="font-size:0.85rem; margin-top:0.25rem;">${proj.description || ""}</p>
            ${bulletsHtml}
        `;
        elements.profileTimeline.appendChild(item);
    });
    
    if (experiences.length === 0 && projects.length === 0) {
        elements.profileTimeline.innerHTML = "<p class='text-muted'>No experiences or projects listed.</p>";
    }
}

// ── Job Feed & Scraper ──
function initJobFeed() {
    elements.jobSearch.addEventListener("input", (e) => {
        state.filters.search = e.target.value.trim();
        debounce(fetchJobs, 300)();
    });
    
    elements.portalFilter.addEventListener("change", (e) => {
        state.filters.portal = e.target.value;
        fetchJobs();
    });
    
    elements.btnScrape.addEventListener("click", () => {
        triggerScrape();
    });
}

async function fetchJobs() {
    let url = `${API_BASE}/jobs?limit=30`;
    if (state.filters.portal) {
        url += `&portal=${state.filters.portal}`;
    }
    if (state.filters.search) {
        url += `&search=${encodeURIComponent(state.filters.search)}`;
    }
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            state.jobs = data.jobs || [];
            renderJobs(state.jobs);
        }
    } catch (e) {
        loggerError(e);
        showToast("Failed to retrieve jobs from backend database.", true);
    }
}

function renderJobs(jobs) {
    elements.jobsList.innerHTML = "";
    elements.resultsCount.textContent = `${jobs.length} internships found`;
    
    if (jobs.length === 0) {
        elements.jobsList.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-briefcase empty-icon"></i>
                <h3>No Internships Found</h3>
                <p>Try searching for a different keyword or trigger a new scrape run.</p>
            </div>
        `;
        return;
    }
    
    jobs.forEach(job => {
        const card = document.createElement("div");
        card.className = "job-card";
        
        // Location text formatting
        let location = job.location || "Remote";
        if (location.length > 25) location = location.substring(0, 22) + "...";
        
        // Stipend text
        let stipend = job.stipend || "Not specified";
        if (stipend.length > 20) stipend = stipend.substring(0, 17) + "...";
        
        card.innerHTML = `
            <div class="job-details">
                <div class="job-title-row">
                    <span class="job-card-title">${job.title}</span>
                    <span class="portal-badge ${job.source_portal}">${job.source_portal}</span>
                </div>
                <span class="job-card-company">${job.company}</span>
                <div class="job-card-meta">
                    <span><i class="fa-solid fa-location-dot"></i> ${location}</span>
                    <span><i class="fa-solid fa-money-bill-wave"></i> ${stipend}</span>
                </div>
            </div>
            <div class="job-card-actions">
                <button class="btn btn-primary btn-match" data-id="${job.id}">
                    <i class="fa-solid fa-wand-magic-sparkles"></i> Copilot
                </button>
            </div>
        `;
        
        card.querySelector(".btn-match").addEventListener("click", () => openJobModal(job));
        elements.jobsList.appendChild(card);
    });
}

async function triggerScrape() {
    elements.btnScrape.disabled = true;
    elements.btnScrape.classList.add("disabled");
    elements.scrapeStatusBanner.classList.remove("hidden");
    
    try {
        const response = await fetch(`${API_BASE}/jobs/scrape?email=${DEFAULT_EMAIL}`, {
            method: "POST"
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Scrape run failed.");
        }
        
        const data = await response.json();
        showToast(`Scrape completed! Found ${data.total_scraped || 0} jobs.`);
        fetchJobs();
        
    } catch (e) {
        loggerError(e);
        showToast(e.message || "An error occurred during scraping.", true);
    } finally {
        elements.btnScrape.disabled = false;
        elements.btnScrape.classList.remove("disabled");
        elements.scrapeStatusBanner.classList.add("hidden");
    }
}

// ── Modal & Copilot Workspace ──
function initModal() {
    elements.modalClose.addEventListener("click", closeJobModal);
    
    elements.copilotTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const subtab = tab.getAttribute("data-subtab");
            switchSubtab(subtab);
        });
    });
    
    elements.modeKeyword.addEventListener("click", () => {
        if (state.scoringMode !== "keyword") {
            state.scoringMode = "keyword";
            elements.modeKeyword.classList.add("active");
            elements.modeAI.classList.remove("active");
            evaluateMatch();
        }
    });
    
    elements.modeAI.addEventListener("click", () => {
        if (state.scoringMode !== "ai") {
            state.scoringMode = "ai";
            elements.modeAI.classList.add("active");
            elements.modeKeyword.classList.remove("active");
            evaluateMatch();
        }
    });
    
    elements.btnRunTailoring.addEventListener("click", () => {
        generateTailoring();
    });
    
    elements.btnSaveDraft.addEventListener("click", () => {
        saveApplicationDraft("draft");
    });
    
    elements.btnOpenSendOutreach.addEventListener("click", () => {
        openOutreachModal();
    });
    
    document.querySelectorAll(".btn-copy").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const textEl = document.getElementById(targetId);
            if (textEl) {
                navigator.clipboard.writeText(textEl.textContent || textEl.innerText);
                showToast("Copied content to clipboard!");
            }
        });
    });
}

function openJobModal(job) {
    state.selectedJob = job;
    state.scoringMode = "keyword";
    
    elements.modeKeyword.classList.add("active");
    elements.modeAI.classList.remove("active");
    switchSubtab("match-analysis");
    
    elements.modalPortal.className = `portal-badge ${job.source_portal}`;
    elements.modalPortal.textContent = job.source_portal;
    elements.modalTitle.textContent = job.title;
    elements.modalCompany.textContent = job.company;
    elements.modalLocation.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${job.location || "Remote"}`;
    elements.modalStipend.innerHTML = `<i class="fa-solid fa-money-bill-wave"></i> ${job.stipend || "Not specified"}`;
    elements.modalJDText.textContent = job.jd_text;
    
    elements.btnRunTailoring.classList.remove("hidden");
    elements.tailoringResultsView.classList.add("hidden");
    elements.tailorLoadingState.classList.add("hidden");
    
    elements.modalContainer.classList.remove("hidden");
    evaluateMatch();
}

function closeJobModal() {
    elements.modalContainer.classList.add("hidden");
    state.selectedJob = null;
}

function switchSubtab(subtab) {
    elements.copilotTabs.forEach(tab => {
        if (tab.getAttribute("data-subtab") === subtab) {
            tab.classList.add("active");
        } else {
            tab.classList.remove("active");
        }
    });
    
    elements.subtabPanes.forEach(pane => {
        if (pane.id === `subtab-${subtab}`) {
            pane.classList.add("active");
        } else {
            pane.classList.remove("active");
        }
    });
}

async function evaluateMatch() {
    if (!state.selectedJob) return;
    
    const jobId = state.selectedJob.id;
    const useAi = state.scoringMode === "ai";
    
    updateCircularScore(0, "...");
    elements.analysisReason.textContent = "Calculating match score...";
    elements.analysisMatchingSkills.innerHTML = "";
    elements.analysisMissingSkills.innerHTML = "";
    
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/match?email=${DEFAULT_EMAIL}&use_ai=${useAi}`);
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to retrieve match score.");
        }
        
        const data = await response.json();
        
        if (data.success && data.match) {
            const score = data.match.score;
            const matchDetails = data.match;
            
            updateCircularScore(score);
            elements.analysisReason.textContent = matchDetails.reason || "Relevance complete.";
            
            elements.analysisMatchingSkills.innerHTML = "";
            const matched = matchDetails.matched_skills || [];
            if (matched.length > 0) {
                matched.forEach(s => {
                    const span = document.createElement("span");
                    span.className = "skill-chip";
                    span.style.borderColor = "var(--success)";
                    span.textContent = s;
                    elements.analysisMatchingSkills.appendChild(span);
                });
            } else {
                elements.analysisMatchingSkills.innerHTML = "<p class='text-muted' style='font-size:0.8rem;'>0 overlapping skills</p>";
            }
            
            elements.analysisMissingSkills.innerHTML = "";
            const missing = matchDetails.missing_skills || [];
            if (missing.length > 0) {
                missing.forEach(s => {
                    const span = document.createElement("span");
                    span.className = "skill-chip";
                    span.textContent = s;
                    elements.analysisMissingSkills.appendChild(span);
                });
            } else {
                elements.analysisMissingSkills.innerHTML = "<p class='text-muted' style='font-size:0.8rem;'>All profile skills relevant</p>";
            }
            
            if (matchDetails.recommendation) {
                elements.analysisRec.textContent = matchDetails.recommendation;
                elements.recommendationBlock.classList.remove("hidden");
            } else {
                elements.recommendationBlock.classList.add("hidden");
            }
        }
        
    } catch (e) {
        loggerError(e);
        updateCircularScore(0, "ERR");
        elements.analysisReason.textContent = e.message || "Failed to evaluate matching criteria.";
    }
}

function updateCircularScore(score, overrideText = null) {
    elements.modalScoreVal.textContent = overrideText !== null ? overrideText : score;
    
    const circumference = 213.6;
    const offset = circumference - (score / 100) * circumference;
    elements.modalCircleScore.style.strokeDashoffset = offset;
    
    if (overrideText === "...") {
        elements.modalCircleScore.style.stroke = "var(--text-muted)";
    } else if (score >= 80) {
        elements.modalCircleScore.style.stroke = "var(--success)";
    } else if (score >= 50) {
        elements.modalCircleScore.style.stroke = "var(--warning)";
    } else {
        elements.modalCircleScore.style.stroke = "var(--danger)";
    }
}

async function generateTailoring() {
    if (!state.selectedJob) return;
    
    elements.btnRunTailoring.classList.add("hidden");
    elements.tailorLoadingState.classList.remove("hidden");
    
    try {
        const jobId = state.selectedJob.id;
        const response = await fetch(`${API_BASE}/jobs/${jobId}/tailor?email=${DEFAULT_EMAIL}`, {
            method: "POST"
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Tailoring request failed.");
        }
        
        const data = await response.json();
        
        if (data.success) {
            elements.tailoredBulletsText.textContent = typeof data.tailored_resume === 'string' ? data.tailored_resume : JSON.stringify(data.tailored_resume, null, 2);
            elements.tailoredLetterText.textContent = data.cover_letter || "";
            
            elements.tailorLoadingState.classList.add("hidden");
            elements.tailoringResultsView.classList.remove("hidden");
            showToast("Gemini completed resume tailoring successfully!");
        }
        
    } catch (e) {
        loggerError(e);
        elements.btnRunTailoring.classList.remove("hidden");
        elements.tailorLoadingState.classList.add("hidden");
        showToast(e.message || "Tailoring failed. Please check rate limits.", true);
    }
}

// ── Save Draft & Outreach Actions ──
async function saveApplicationDraft(statusType = "draft") {
    if (!state.selectedJob) return null;
    
    try {
        const response = await fetch(`${API_BASE}/applications`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: state.selectedJob.id,
                email: DEFAULT_EMAIL,
                tailored_resume: elements.tailoredBulletsText.textContent,
                cover_letter: elements.tailoredLetterText.textContent,
                status: statusType
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to save draft.");
        }
        
        const data = await response.json();
        if (statusType === "draft") {
            showToast("Application draft saved successfully!");
        }
        return data.application_id;
    } catch (e) {
        loggerError(e);
        showToast(e.message || "Failed to save application details.", true);
        return null;
    }
}

// ── Outreach Sub-Modal Logic ──
function initOutreachModal() {
    elements.outreachModalClose.addEventListener("click", closeOutreachModal);
    
    elements.btnConfirmSendOutreach.addEventListener("click", async () => {
        const toEmail = elements.outreachEmailInput.value.trim();
        const subject = elements.outreachSubjectInput.value.trim();
        
        if (!toEmail || !toEmail.includes("@")) {
            showToast("Error: Please specify a valid recruiter email address.", true);
            return;
        }
        
        // 1. Save draft details first
        const appId = await saveApplicationDraft("applied");
        if (!appId) return;
        
        // 2. Dispatch
        await sendOutreachEmail(appId, toEmail, subject);
    });
}

function openOutreachModal() {
    if (!state.selectedJob) return;
    elements.outreachEmailInput.value = "";
    elements.outreachSubjectInput.value = `Application for ${state.selectedJob.title} - Test Student`;
    elements.outreachModalContainer.classList.remove("hidden");
}

function closeOutreachModal() {
    elements.outreachModalContainer.classList.add("hidden");
}

async function sendOutreachEmail(appId, toEmail, subject) {
    elements.btnConfirmSendOutreach.disabled = true;
    elements.btnConfirmSendOutreach.textContent = "Sending...";
    
    try {
        const response = await fetch(`${API_BASE}/applications/${appId}/send`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                to_email: toEmail,
                subject: subject
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Dispatched failed.");
        }
        
        showToast("Outreach email sent and tracked successfully!");
        closeOutreachModal();
        closeJobModal();
        switchTab("kanban"); // redirect directly to Kanban tracker
        
    } catch (e) {
        loggerError(e);
        showToast(e.message || "Failed to send email outreach.", true);
    } finally {
        elements.btnConfirmSendOutreach.disabled = false;
        elements.btnConfirmSendOutreach.textContent = "Dispatch Email";
    }
}

// ── Kanban Tracker Manager ──
function initKanbanView() {
    elements.btnSimulateWebhook.addEventListener("click", () => {
        simulateRecruiterReply();
    });
}

async function fetchApplications() {
    try {
        const response = await fetch(`${API_BASE}/applications?email=${DEFAULT_EMAIL}`);
        const data = await response.json();
        
        if (data.success) {
            state.applications = data.applications || [];
            renderKanban(state.applications);
        }
    } catch (e) {
        loggerError(e);
        showToast("Failed to fetch applications checklist.", true);
    }
}

function renderKanban(apps) {
    const columns = {
        draft: { el: elements.kanbanDraft, badge: elements.badgeDraft, list: [] },
        applied: { el: elements.kanbanApplied, badge: elements.badgeApplied, list: [] },
        seen: { el: elements.kanbanSeen, badge: elements.badgeSeen, list: [] },
        replied: { el: elements.kanbanReplied, badge: elements.badgeReplied, list: [] },
        interview: { el: elements.kanbanInterview, badge: elements.badgeInterview, list: [] }
    };
    
    // Reset columns HTML and lists
    Object.keys(columns).forEach(status => {
        columns[status].el.innerHTML = "";
        columns[status].list = [];
    });
    
    // Group applications by status
    apps.forEach(app => {
        const status = app.status ? app.status.toLowerCase() : "draft";
        if (columns[status]) {
            columns[status].list.push(app);
        } else if (status === "rejected" || status === "offer") {
            // map rejected/offer to interview for simpler layout or render accordingly
            columns.interview.list.push(app);
        } else {
            columns.draft.list.push(app);
        }
    });
    
    // Render columns
    Object.keys(columns).forEach(status => {
        const col = columns[status];
        col.badge.textContent = col.list.length;
        
        if (col.list.length === 0) {
            col.el.innerHTML = `
                <div class="empty-column-state" style="text-align: center; color: var(--text-muted); font-size: 0.75rem; padding: 2rem 0; border: 1px dashed rgba(255,255,255,0.03); border-radius: 8px;">
                    Column Empty
                </div>
            `;
            return;
        }
        
        col.list.forEach(app => {
            const card = document.createElement("div");
            card.className = "kanban-card";
            
            const jobTitle = app.job ? app.job.title : "Tailored Resume Upload";
            const company = app.job ? app.job.company : "Independent Profile";
            const portal = app.job ? app.job.source_portal : "Direct";
            
            card.innerHTML = `
                <div class="kanban-card-title">${jobTitle}</div>
                <div class="kanban-card-company">${company}</div>
                <div class="kanban-card-meta">
                    <span class="portal-badge ${portal}">${portal}</span>
                    <span>v${status === "draft" ? "Draft" : status.toUpperCase()}</span>
                </div>
            `;
            
            // Allow dragging or clicking to advance status
            card.addEventListener("click", () => {
                openKanbanCardMenu(app);
            });
            col.el.appendChild(card);
        });
    });
}

function openKanbanCardMenu(app) {
    // Allows student to change card status easily via prompt selector
    const current = app.status;
    const statuses = ["draft", "applied", "seen", "replied", "interview", "offer", "rejected"];
    const promptMessage = `Move "${app.job ? app.job.title : 'Application'}" status from "${current}" to:\n` + 
                         statuses.map((s, idx) => `  [${idx}] ${s}`).join("\n");
                         
    const selection = prompt(promptMessage, statuses.indexOf(current));
    if (selection !== null && selection.trim() !== "") {
        const val = parseInt(selection);
        if (val >= 0 && val < statuses.length) {
            const newStatus = statuses[val];
            if (newStatus !== current) {
                updateApplicationStatus(app.id, newStatus);
            }
        }
    }
}

async function updateApplicationStatus(appId, newStatus) {
    try {
        const response = await fetch(`${API_BASE}/applications/${appId}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (!response.ok) throw new Error("Failed to update status.");
        
        showToast(`Moved application status to ${newStatus}!`);
        fetchApplications(); // refresh columns
    } catch (e) {
        loggerError(e);
        showToast("Error updating application status.", true);
    }
}

async function simulateRecruiterReply() {
    const email = elements.webhookEmail.value.trim();
    if (!email || !email.includes("@")) {
        showToast("Error: Please provide a valid recruiter email address to simulate reply.", true);
        return;
    }
    
    elements.btnSimulateWebhook.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE}/applications/inbound-webhook`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sender_email: email,
                subject: "Re: Internship Application",
                body: "Hi! Thanks for reaching out. We would love to schedule an interview."
            })
        });
        
        if (!response.ok) throw new Error("Webhook simulator failed.");
        
        const data = await response.json();
        if (data.success) {
            showToast("Recruiter reply successfully simulated! Kanban board updated.");
            fetchApplications();
        } else {
            showToast(`Simulation ignored: ${data.message}`, true);
        }
    } catch (e) {
        loggerError(e);
        showToast("Reply simulation failed.", true);
    } finally {
        elements.btnSimulateWebhook.disabled = false;
    }
}

// ── Backend Bootstrapping / Init Load ──
async function loadProfileAndJobs() {
    try {
        const response = await fetch(`${API_BASE}/jobs?limit=5`);
        if (response.ok) {
            fetchJobs();
            checkAndLoadActiveProfile();
        }
    } catch (e) {
        loggerError(e);
        showToast("Warning: Backend API unreachable. Check if server is running.", true);
    }
}

async function checkAndLoadActiveProfile() {
    try {
        const response = await fetch(`${API_BASE}/resume/active?email=${DEFAULT_EMAIL}`);
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.parsed_resume) {
                renderProfile(data.parsed_resume, data.version);
            }
        }
    } catch (e) {
        // Ignored
    }
}

// ── Helpers ──
function showToast(message, isError = false) {
    elements.toast.textContent = message;
    elements.toast.className = "toast";
    if (isError) {
        elements.toast.style.borderColor = "var(--danger)";
        elements.toast.style.boxShadow = "0 4px 20px rgba(239, 68, 68, 0.3)";
    } else {
        elements.toast.style.borderColor = "var(--primary-light)";
        elements.toast.style.boxShadow = "0 4px 20px rgba(99,102,241,0.3)";
    }
    elements.toast.classList.remove("hidden");
    
    setTimeout(() => {
        elements.toast.classList.add("hidden");
    }, 3000);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function loggerError(e) {
    console.error("[AutoIntern Error]", e);
}
