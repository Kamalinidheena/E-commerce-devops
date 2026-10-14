/**
 * IncidentPulse Responsive Canvas Chart Engine
 * Lightweight, zero-dependency HTML5 Canvas chart for real response-time telemetry.
 */

class ResponseTimeChart {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.thresholdMs = options.thresholdMs || 500;
    this.dataPoints = [];
    this.hoverIndex = -1;

    this.init();
  }

  init() {
    this.resize();
    window.addEventListener("resize", () => {
      this.resize();
      this.render();
    });

    // Mouse hover tracking
    this.canvas.addEventListener("mousemove", (e) => this.handleMouseMove(e));
    this.canvas.addEventListener("mouseleave", () => {
      this.hoverIndex = -1;
      this.render();
    });
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = Math.max(220, Math.min(320, rect.height || 260));

    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;

    this.ctx.scale(dpr, dpr);
  }

  setData(checks, thresholdMs) {
    if (thresholdMs) this.thresholdMs = thresholdMs;
    // Checks are ordered descending by time from API, reverse to chronological order
    this.dataPoints = (checks || []).slice().reverse().map(c => ({
      time: new Date(c.created_at),
      ms: c.response_time_ms || 0,
      status: c.status,
      code: c.http_status,
      error: c.error_message
    }));
    this.render();
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    if (!this.dataPoints || this.dataPoints.length === 0) {
      // Honest empty state
      ctx.fillStyle = "#777466";
      ctx.font = "14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("No check data recorded yet. Checks will plot here automatically.", w / 2, h / 2);
      return;
    }

    const padLeft = 50;
    const padRight = 30;
    const padTop = 25;
    const padBottom = 35;

    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    // Determine max ms for Y-axis scale
    const maxVal = Math.max(
      this.thresholdMs * 1.2,
      ...this.dataPoints.map(d => d.ms),
      50
    );

    // Draw horizontal grid lines
    ctx.strokeStyle = "#F0E6BF";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#9E9A89";
    ctx.font = "11px monospace";
    ctx.textAlign = "right";

    const gridSteps = 4;
    for (let i = 0; i <= gridSteps; i++) {
      const val = Math.round((maxVal / gridSteps) * i);
      const y = padTop + plotH - (val / maxVal) * plotH;

      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(w - padRight, y);
      ctx.stroke();

      ctx.fillText(`${val}ms`, padLeft - 8, y + 3);
    }

    // Draw threshold line (Amber dashed)
    if (this.thresholdMs <= maxVal) {
      const threshY = padTop + plotH - (this.thresholdMs / maxVal) * plotH;
      ctx.save();
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = "#D97706";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(padLeft, threshY);
      ctx.lineTo(w - padRight, threshY);
      ctx.stroke();
      ctx.fillStyle = "#D97706";
      ctx.textAlign = "left";
      ctx.fillText(`Alert Threshold (${this.thresholdMs}ms)`, padLeft + 6, threshY - 6);
      ctx.restore();
    }

    // Map data points to coordinates
    const points = this.dataPoints.map((d, idx) => {
      const x = this.dataPoints.length === 1 
        ? padLeft + plotW / 2 
        : padLeft + (idx / (this.dataPoints.length - 1)) * plotW;
      const y = padTop + plotH - (Math.min(d.ms, maxVal) / maxVal) * plotH;
      return { x, y, data: d };
    });

    // Draw area fill
    ctx.beginPath();
    ctx.moveTo(points[0].x, padTop + plotH);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, padTop + plotH);
    ctx.closePath();
    ctx.fillStyle = "rgba(255, 230, 128, 0.35)";
    ctx.fill();

    // Draw line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.strokeStyle = "#302F25";
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.stroke();

    // Draw points
    points.forEach((p, idx) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, idx === this.hoverIndex ? 6 : 3.5, 0, Math.PI * 2);
      ctx.fillStyle = p.data.status === "UP" ? (p.data.ms > this.thresholdMs ? "#D97706" : "#2E7D32") : "#DC2626";
      ctx.fill();
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    // Tooltip on hover
    if (this.hoverIndex >= 0 && this.hoverIndex < points.length) {
      const hp = points[this.hoverIndex];
      const timeStr = hp.data.time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const label = `${hp.data.ms}ms (${hp.data.status}) - ${timeStr}`;

      ctx.save();
      ctx.font = "bold 12px sans-serif";
      const textWidth = ctx.measureText(label).width;
      const boxW = textWidth + 18;
      const boxH = 28;
      let boxX = hp.x - boxW / 2;
      let boxY = hp.y - 38;

      if (boxX < 10) boxX = 10;
      if (boxX + boxW > w - 10) boxX = w - boxW - 10;
      if (boxY < 10) boxY = hp.y + 12;

      ctx.fillStyle = "#302F25";
      ctx.beginPath();
      ctx.roundRect(boxX, boxY, boxW, boxH, 6);
      ctx.fill();

      ctx.fillStyle = "#FFFDF4";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, boxX + boxW / 2, boxY + boxH / 2);
      ctx.restore();
    }
  }

  handleMouseMove(e) {
    if (!this.dataPoints || this.dataPoints.length === 0) return;
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;

    const padLeft = 50;
    const padRight = 30;
    const plotW = this.width - padLeft - padRight;

    if (this.dataPoints.length === 1) {
      this.hoverIndex = 0;
    } else {
      let closestIdx = 0;
      let minDiff = Infinity;
      this.dataPoints.forEach((_, idx) => {
        const x = padLeft + (idx / (this.dataPoints.length - 1)) * plotW;
        const diff = Math.abs(x - mouseX);
        if (diff < minDiff) {
          minDiff = diff;
          closestIdx = idx;
        }
      });
      this.hoverIndex = closestIdx;
    }
    this.render();
  }
}

window.ResponseTimeChart = ResponseTimeChart;
