"""Signal Quality Score."""
def compute_signal_quality(alert_q,escalation_q,degradation_q,recovery_q):
    scores={}
    # Alert Quality (0~100)
    mr=alert_q.get("meaningful_ratio",0)
    scores["alert_quality"]=min(100,int(mr*100))
    # Noise Ratio (0~100, \ub0ae\uc744\uc218\ub85d \uc88b\uc74c)
    nr=alert_q.get("noisy_ratio",0)
    scores["noise_ratio"]=min(100,int(nr*100))
    # Escalation Quality
    er=escalation_q.get("effective_ratio",0)
    scores["escalation_quality"]=min(100,int(er*100))
    # Recovery Quality
    re=recovery_q.get("effectiveness",0)
    scores["recovery_quality"]=min(100,int(re*100))
    # Stability Accuracy
    dc=degradation_q.get("confidence",0)
    scores["stability_accuracy"]=min(100,int(dc*100))
    # Overall (\uac00\uc911 \ud3c9\uade0)
    w={"alert_quality":0.25,"noise_ratio":-0.15,"escalation_quality":0.25,"recovery_quality":0.2,"stability_accuracy":0.15}
    overall=sum(scores[k]*v for k,v in w.items())
    scores["overall"]=max(0,min(100,int(overall+50)))  # noise\ub294 \uac10\uc810
    return scores
