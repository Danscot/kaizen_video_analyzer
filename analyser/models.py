"""
analyser/models.py
Stores every analysis result in SQLite so exports survive server restarts
and we have a full history of past jobs.
"""
import uuid
from django.db import models


class AnalysisJob(models.Model):

    TRACK_CHOICES = [
        ("content", "Content Analysis"),
        ("visual",  "Visual / Motion Analysis"),
        ("full",    "Full Analysis"),
    ]

    STATUS_CHOICES = [
        ("pending",    "Pending"),
        ("running",    "Running"),
        ("complete",   "Complete"),
        ("error",      "Error"),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    # Source info
    source_name = models.CharField(max_length=512, default="")
    source_url  = models.URLField(max_length=2048, blank=True, default="")
    track       = models.CharField(max_length=16, choices=TRACK_CHOICES, default="content")
    status      = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")

    # Model choices used
    whisper_model = models.CharField(max_length=64,  default="base")
    gemini_model  = models.CharField(max_length=64,  default="gemini-2.5-flash")
    gemma_model   = models.CharField(max_length=64,  default="gemma-4-31b-it")

    # Results (stored as JSON text — avoids JSONField migration headaches)
    transcript       = models.TextField(blank=True, default="")
    analysis_json    = models.TextField(blank=True, default="")   # content analysis dict
    visual_json      = models.TextField(blank=True, default="")   # raw frame batches
    design_json      = models.TextField(blank=True, default="")   # design context dict
    planner_markdown = models.TextField(blank=True, default="")

    # Stats
    frames_extracted = models.IntegerField(default=0)
    scenes_analysed  = models.IntegerField(default=0)
    word_count       = models.IntegerField(default=0)

    # Error message if status == 'error'
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Analysis Job"

    def __str__(self):
        return f"{self.track} / {self.source_name} [{self.status}]"

    @property
    def short_id(self):
        return str(self.id)[:8]

    def to_export_dict(self):
        """Return the full result dict used for JSON / PDF export."""
        import json
        d = {
            "meta": {
                "job_id":        str(self.id),
                "source":        self.source_name,
                "source_url":    self.source_url,
                "analysed_at":   self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "whisper_model": self.whisper_model,
                "gemini_model":  self.gemini_model,
                "gemma_model":   self.gemma_model,
                "track":         self.track,
            },
            "transcript": self.transcript,
        }
        if self.analysis_json:
            try:
                d["analysis"] = json.loads(self.analysis_json)
            except Exception:
                d["analysis"] = {}
        if self.design_json:
            try:
                d["design_context"] = json.loads(self.design_json)
            except Exception:
                d["design_context"] = {}
        if self.planner_markdown:
            d["planner_markdown"] = self.planner_markdown
        if self.visual_json:
            try:
                d["visual_analysis"] = json.loads(self.visual_json)
            except Exception:
                d["visual_analysis"] = {}
        return d
