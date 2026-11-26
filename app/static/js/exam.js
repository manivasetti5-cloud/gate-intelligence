(function () {
  const rawEl = document.getElementById("initial-exam-state");
  if (!rawEl) return;

  const state = JSON.parse(rawEl.textContent);
  const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
  const attemptId = state.attempt_id;
  const saveUrl = `/assessments/exam/${attemptId}/save`;
  const submitUrl = `/assessments/exam/${attemptId}/submit`;

  let currentIdx = Math.min(state.current_question_index || 0, Math.max(0, state.questions.length - 1));
  let remainingSeconds = state.remaining_seconds || 0;
  let lastTick = Date.now();
  let isSubmitting = false;
  let countdownHandle = null;

  const timerEl = document.getElementById("timerDisplay");
  const saveStatusEl = document.getElementById("saveStatus");
  const paletteGrid = document.getElementById("paletteGrid");
  const qHeader = document.getElementById("qHeader");
  const qSection = document.getElementById("qSection");
  const qTypeBadge = document.getElementById("qTypeBadge");
  const qSourceBadge = document.getElementById("qSourceBadge");
  const qMarks = document.getElementById("qMarks");
  const qNegMarks = document.getElementById("qNegMarks");
  const qStatement = document.getElementById("qStatement");
  const qImages = document.getElementById("qImages");
  const qInputArea = document.getElementById("qInputArea");

  function formatTime(sec) {
    const s = Math.max(0, sec);
    const hrs = String(Math.floor(s / 3600)).padStart(2, "0");
    const mins = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const secs = String(s % 60).padStart(2, "0");
    return `${hrs}:${mins}:${secs}`;
  }

  function hasAnswer(q) {
    if (q.question_type === "NAT") {
      return (
        q.response.nat_answer_value !== null &&
        q.response.nat_answer_value !== undefined &&
        String(q.response.nat_answer_value).trim() !== ""
      );
    }
    return Array.isArray(q.response.selected_options) && q.response.selected_options.length > 0;
  }

  function renderPalette() {
    paletteGrid.innerHTML = "";
    state.questions.forEach((q, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `palette-btn st-${q.response.palette_status} ${idx === currentIdx ? "current" : ""}`;
      btn.textContent = q.order_index;
      btn.title = `Q${q.order_index} (${q.section_name})`;
      btn.addEventListener("click", () => goToQuestion(idx));
      paletteGrid.appendChild(btn);
    });
  }

  function readCurrentInputs(q) {
    if (!q) return;
    if (q.question_type === "NAT") {
      const inp = document.getElementById("natInput");
      const raw = inp ? inp.value.trim() : "";
      q.response.nat_answer_value = raw === "" ? null : raw;
      q.response.selected_options = [];
    } else {
      const checked = Array.from(document.querySelectorAll('input[name="optChoice"]:checked')).map(
        (el) => el.value
      );
      q.response.selected_options = checked;
      q.response.nat_answer_value = null;
    }
  }

  function renderQuestion() {
    const q = state.questions[currentIdx];
    if (!q) return;

    if (q.response.palette_status === "not_visited") {
      q.response.palette_status = "visited_unanswered";
    }

    qHeader.textContent = `Question ${q.order_index} of ${state.questions.length}`;
    qSection.textContent = q.section_name;
    qTypeBadge.textContent = q.question_type;
    qSourceBadge.textContent = q.source_type;
    qMarks.textContent = `+${q.marks} Mark${q.marks > 1 ? "s" : ""}`;
    qNegMarks.textContent =
      q.negative_marks > 0 ? `-${q.negative_marks} Negative` : "No Negative Marking";
    qStatement.textContent = q.statement_md;

    // Safely render diagram images via DOM nodes (no HTML injection)
    qImages.innerHTML = "";
    (q.images || []).forEach((img) => {
      const fig = document.createElement("figure");
      fig.className = "mb-2";
      const imageEl = document.createElement("img");
      imageEl.src = `/static/${img.file_path}`;
      imageEl.className = "img-fluid rounded border";
      imageEl.style.maxHeight = "280px";
      imageEl.alt = img.caption || "Question diagram";
      fig.appendChild(imageEl);
      qImages.appendChild(fig);
    });

    // Safely render options/NAT input using textContent so '<' and '>' math symbols never break
    qInputArea.innerHTML = "";
    if (q.question_type === "NAT") {
      const lbl = document.createElement("label");
      lbl.className = "form-label fw-semibold small";
      lbl.htmlFor = "natInput";
      lbl.textContent = "Numerical Answer (Enter integer or decimal):";

      const inp = document.createElement("input");
      inp.type = "text";
      inp.inputMode = "decimal";
      inp.className = "form-control form-control-lg";
      inp.style.maxWidth = "280px";
      inp.id = "natInput";
      inp.placeholder = "e.g. 12.5";
      inp.value =
        q.response.nat_answer_value !== null && q.response.nat_answer_value !== undefined
          ? String(q.response.nat_answer_value)
          : "";

      qInputArea.appendChild(lbl);
      qInputArea.appendChild(inp);
    } else {
      const inputType = q.question_type === "MSQ" ? "checkbox" : "radio";
      const selectedSet = new Set(q.response.selected_options || []);
      q.options.forEach((opt) => {
        const label = document.createElement("label");
        label.className = "option-card d-flex align-items-start gap-3 mb-2";

        const input = document.createElement("input");
        input.className = "form-check-input mt-1";
        input.type = inputType;
        input.name = "optChoice";
        input.value = opt.label;
        input.checked = selectedSet.has(opt.label);

        const textWrap = document.createElement("div");
        const strong = document.createElement("strong");
        strong.className = "me-2";
        strong.textContent = `(${opt.label})`;
        const span = document.createElement("span");
        span.textContent = opt.text;

        textWrap.appendChild(strong);
        textWrap.appendChild(span);
        label.appendChild(input);
        label.appendChild(textWrap);
        qInputArea.appendChild(label);
      });
    }

    document.getElementById("prevBtn").disabled = currentIdx === 0;
    renderPalette();
  }

  async function persistQuestion(q, markReview = false) {
    if (!q) return false;
    readCurrentInputs(q);
    const answered = hasAnswer(q);
    if (markReview) {
      q.response.palette_status = answered ? "answered_and_marked" : "marked_for_review";
    } else {
      q.response.palette_status = answered ? "answered" : "visited_unanswered";
    }

    const now = Date.now();
    const delta = Math.max(0, Math.round((now - lastTick) / 1000));
    lastTick = now;

    saveStatusEl.textContent = "Saving...";
    try {
      const res = await fetch(saveUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          test_question_id: q.test_question_id,
          selected_options: q.response.selected_options,
          nat_answer_value: q.response.nat_answer_value,
          palette_status: q.response.palette_status,
          current_question_index: currentIdx,
          time_delta_seconds: delta,
        }),
      });
      if (res.status === 409) {
        isSubmitting = true;
        window.location.href = `/results/${attemptId}`;
        return false;
      }
      const data = await res.json();
      if (!res.ok) {
        saveStatusEl.textContent = data.error || "Invalid input";
        return false;
      }
      if (typeof data.remaining_seconds === "number") {
        remainingSeconds = data.remaining_seconds;
      }
      saveStatusEl.textContent = "Saved";
      renderPalette();
      return true;
    } catch (e) {
      saveStatusEl.textContent = "Offline retry pending";
      renderPalette();
      return false;
    }
  }

  async function goToQuestion(idx) {
    const currentQ = state.questions[currentIdx];
    if (currentQ) {
      await persistQuestion(currentQ, currentQ.response.palette_status.includes("marked"));
    }
    currentIdx = idx;
    renderQuestion();
  }

  document.getElementById("saveNextBtn").addEventListener("click", async () => {
    await persistQuestion(state.questions[currentIdx], false);
    if (currentIdx + 1 < state.questions.length) {
      currentIdx += 1;
      renderQuestion();
    }
  });

  document.getElementById("markReviewBtn").addEventListener("click", async () => {
    await persistQuestion(state.questions[currentIdx], true);
    if (currentIdx + 1 < state.questions.length) {
      currentIdx += 1;
      renderQuestion();
    }
  });

  document.getElementById("prevBtn").addEventListener("click", async () => {
    if (currentIdx > 0) {
      await goToQuestion(currentIdx - 1);
    }
  });

  document.getElementById("clearBtn").addEventListener("click", async () => {
    const q = state.questions[currentIdx];
    q.response.selected_options = [];
    q.response.nat_answer_value = null;
    q.response.palette_status = "visited_unanswered";
    renderQuestion();
    await persistQuestion(q, false);
  });

  document.getElementById("openSubmitModalBtn").addEventListener("click", async () => {
    const currentQ = state.questions[currentIdx];
    await persistQuestion(currentQ, currentQ.response.palette_status.includes("marked"));
    const counts = {
      answered: 0,
      visited_unanswered: 0,
      marked_for_review: 0,
      answered_and_marked: 0,
      not_visited: 0,
    };
    state.questions.forEach((q) => {
      counts[q.response.palette_status] = (counts[q.response.palette_status] || 0) + 1;
    });
    document.getElementById("submitSummaryList").innerHTML = `
      <li class="list-group-item d-flex justify-content-between"><span>Answered</span><strong>${counts.answered}</strong></li>
      <li class="list-group-item d-flex justify-content-between"><span>Answered &amp; Marked for Review</span><strong>${counts.answered_and_marked}</strong></li>
      <li class="list-group-item d-flex justify-content-between"><span>Marked for Review (Unanswered)</span><strong>${counts.marked_for_review}</strong></li>
      <li class="list-group-item d-flex justify-content-between"><span>Visited but Unanswered</span><strong>${counts.visited_unanswered}</strong></li>
      <li class="list-group-item d-flex justify-content-between"><span>Not Visited</span><strong>${counts.not_visited}</strong></li>
    `;
    const modal = new bootstrap.Modal(document.getElementById("submitModal"));
    modal.show();
  });

  document.getElementById("finalSubmitForm").addEventListener("submit", () => {
    isSubmitting = true;
  });

  window.addEventListener("beforeunload", (e) => {
    if (!isSubmitting && remainingSeconds > 0) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  async function autoSubmit() {
    if (isSubmitting) return;
    isSubmitting = true;
    if (countdownHandle) clearInterval(countdownHandle);
    const ok = await persistQuestion(state.questions[currentIdx], false);
    if (!ok && window.location.pathname.startsWith("/results/")) return;
    try {
      const res = await fetch(submitUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ auto_submit: true }),
      });
      const data = await res.json();
      window.location.href = data.redirect_url || `/results/${attemptId}`;
    } catch (e) {
      window.location.href = `/results/${attemptId}`;
    }
  }

  // Periodic background autosave every 30s
  setInterval(() => {
    if (!isSubmitting && state.questions[currentIdx]) {
      const q = state.questions[currentIdx];
      persistQuestion(q, q.response.palette_status.includes("marked"));
    }
  }, 30000);

  timerEl.textContent = formatTime(remainingSeconds);
  countdownHandle = setInterval(() => {
    remainingSeconds = Math.max(0, remainingSeconds - 1);
    timerEl.textContent = formatTime(remainingSeconds);
    if (remainingSeconds <= 300) {
      timerEl.classList.add("text-danger");
    }
    if (remainingSeconds <= 0) {
      autoSubmit();
    }
  }, 1000);

  // Scientific Calculator Widget
  const calcInput = document.getElementById("calcExpression");
  const calcOutput = document.getElementById("calcResult");
  const calcEvalBtn = document.getElementById("calcEvalBtn");
  if (calcInput && calcEvalBtn && calcOutput) {
    const evaluateExpr = () => {
      try {
        const expr = calcInput.value
          .replace(/\^/g, "**")
          .replace(/\bpi\b/gi, "Math.PI")
          .replace(/\be\b/g, "Math.E")
          .replace(/\bsin\(/gi, "Math.sin(")
          .replace(/\bcos\(/gi, "Math.cos(")
          .replace(/\btan\(/gi, "Math.tan(")
          .replace(/\blog10\(/gi, "Math.log10(")
          .replace(/\bln\(/gi, "Math.log(")
          .replace(/\bsqrt\(/gi, "Math.sqrt(")
          .replace(/\babs\(/gi, "Math.abs(");
        if (!/^[0-9+\-*/().,\sMathPIEsincoagrtlbq]+$/.test(expr)) {
          calcOutput.textContent = "Invalid expression";
          return;
        }
        const val = Function(`"use strict"; return (${expr});`)();
        calcOutput.textContent = Number.isFinite(val) ? String(Number(val.toPrecision(10))) : "Error";
      } catch (err) {
        calcOutput.textContent = "Syntax error";
      }
    };
    calcEvalBtn.addEventListener("click", evaluateExpr);
    calcInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        evaluateExpr();
      }
    });
  }

  renderQuestion();
})();
