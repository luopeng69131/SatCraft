"""A compact starting policy illustrating the joint action interface."""


def policy(observation, memory):
    jobs = observation["jobs"]
    ready = [job for job in jobs if job["ready"]]
    history = observation["past_rates"][-4:]
    star = sum(pair[0] for pair in history) / max(1, len(history))
    cell = sum(pair[1] for pair in history) / max(1, len(history))
    modes = {}
    for job in ready:
        if job["status"] == "wait":
            remaining = job["due"] - observation["t"]
            saving = job["raw"] * (1 - job["ratio"])
            compute = (
                saving / max(star, 1.0) > job["cpu"] and job["cpu"] + 1 < remaining
            )
            modes[job["id"]] = "compress" if compute else "raw"
    cpu_jobs = [
        job
        for job in ready
        if job["status"] == "cpu" or modes.get(job["id"]) == "compress"
    ]
    net_jobs = [
        job for job in ready if job["status"] == "net" or modes.get(job["id"]) == "raw"
    ]
    order = sorted(net_jobs, key=lambda job: (job["due"], job["id"]))
    demand = sum(job["tx_left"] for job in net_jobs)
    return {
        "modes": modes,
        "cpu_job": min(cpu_jobs, key=lambda job: (job["due"], job["id"]))["id"]
        if cpu_jobs
        else None,
        "net_order": [job["id"] for job in order],
        "cell_enabled": bool(net_jobs and cell > 0 and demand > star),
        "cell_cap": min(cell, observation["cell_budget"]),
    }
