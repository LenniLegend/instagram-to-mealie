import threading
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_migrate import Migrate

import config
from models import db, Job
from workers import process_scraping_job

app = Flask(__name__)
app.config.from_object(config.Config)

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# Create tables
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/submit', methods=['POST'])
def submit_job():
    url = request.form.get('url')
    platform = request.form.get('platform')
    target = request.form.get('target')
    
    if not url:
        flash('Please enter a URL', 'error')
        return redirect(url_for('index'))
    
    # Create a new job
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        url=url,
        platform=platform,
        target=target,
        status='pending',
        created_at=datetime.now()
    )
    
    db.session.add(job)
    db.session.commit()
    
    # Start the job in a background thread
    threading.Thread(
        target=process_scraping_job,
        args=(job_id,),
        daemon=True
    ).start()
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<job_id>')
def view_job(job_id):
    job = Job.query.get_or_404(job_id)
    return render_template('job.html', job=job)

@app.route('/api/job/<job_id>/delete', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    return redirect(url_for('history'))

@app.route('/api/job/<job_id>')
def get_job_status(job_id):
    job = Job.query.get_or_404(job_id)
    return jsonify({
        'status': job.status,
        'progress': job.progress,
        'message': job.message,
        'result_url': job.result_url if job.status == 'completed' else None
    })

@app.route('/history')
def history():
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    return render_template('history.html', jobs=jobs)


@app.route('/mealie')
def mealie_info():
    from os import getenv
    base_url = getenv('BASE_URL_MEALIE')
    return render_template('mealie_url.html', base_url=base_url)

@app.route('/api/jobs')
def api_jobs():
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    return jsonify([{
        'id': job.id,
        'url': job.url,
        'platform': job.platform,
        'target': job.target,
        'status': job.status,
        'created_at': job.created_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None
    } for job in jobs])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)