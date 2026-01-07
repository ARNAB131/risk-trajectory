require "sinatra"
require "json"
require "mail"

set :bind, "0.0.0.0"
set :port, 4567

def smtp_configured?
  ENV["SMTP_HOST"] && ENV["SMTP_PORT"] && ENV["SMTP_USER"] && ENV["SMTP_PASS"] && ENV["SMTP_FROM"]
end

def send_email(subject, body, to: nil)
  return false unless smtp_configured?
  to ||= ENV["SMTP_USER"]

  Mail.defaults do
    delivery_method :smtp, {
      address: ENV["SMTP_HOST"],
      port: ENV["SMTP_PORT"].to_i,
      user_name: ENV["SMTP_USER"],
      password: ENV["SMTP_PASS"],
      authentication: :plain,
      enable_starttls_auto: true
    }
  end

  mail = Mail.new do
    from    ENV["SMTP_FROM"]
    to      to
    subject subject
    body    body
  end

  mail.deliver!
  true
end

post "/notify" do
  request.body.rewind
  data = JSON.parse(request.body.read) rescue {}

  patient_id = data["patient_id"]
  level = data["level"]
  title = data["title"] || "Risk Trajectory Alert"
  message = data["message"] || ""
  payload = data["payload"] || {}

  puts "[NOTIFY] patient=#{patient_id} level=#{level} title=#{title}"
  puts "  message=#{message}"

  if level == "red" || level == "orange"
    email_subject = "[#{level.upcase}] #{title} - #{patient_id}"
    email_body = <<~BODY
      Risk Trajectory Alert

      Patient: #{patient_id}
      Level: #{level}
      Title: #{title}

      Summary:
      #{message}

      Vitals:
      #{(payload["vitals"] || {}).to_json}

      Outcomes:
      #{(payload["outcomes"] || []).to_json}
    BODY

    sent = send_email(email_subject, email_body)
    puts sent ? "  email=sent" : "  email=skipped (SMTP not configured)"
  end

  content_type :json
  { ok: true }.to_json
end

get "/health" do
  content_type :json
  { ok: true, smtp_configured: smtp_configured? }.to_json
end
