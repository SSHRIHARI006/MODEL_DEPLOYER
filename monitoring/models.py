from django.db import models
from django.conf import settings

class UsageMetric(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    date = models.DateField()

    request_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)

    avg_latency = models.FloatField(default=0)

    class Meta:
        unique_together = ("user", "date")

    def __str__(self):
        return f"{self.user.email} - {self.date}"