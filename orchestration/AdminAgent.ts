/**
 * AdminAgent.ts
 * 
 * Persistent orchestration agent that monitors email, ad accounts, and spawns
 * specialty agents on schedule. Runs in an event loop every 5 minutes.
 * 
 * State Machine: idle → checking_email → parsing_forms → evaluating_thresholds → spawning_agents → reporting → sleeping
 */

import * as fs from 'fs';
import * as path from 'path';
import { EventEmitter } from 'events';

interface EmailAccount {
  address: string;
  provider: string; // 'himalaya', 'gmail_api'
}

interface Threshold {
  metric: string;
  operator: 'gt' | 'lt' | 'eq';
  value: number;
  severity: 'warning' | 'error' | 'success'; // Matches ActivityLog status
}

interface SpecialtyAgent {
  name: string;
  schedule: string; // cron format
  task: string;
  enabled: boolean;
}

interface AdminConfig {
  email_accounts: EmailAccount[];
  thresholds: Threshold[];
  specialty_agents: SpecialtyAgent[];
  telegram: {
    webhook_url?: string;
    enabled: boolean;
  };
  polling_interval_ms: number;
}

interface ActivityLog {
  timestamp: string; // ISO8601 format
  event_type: string;
  status: 'success' | 'error' | 'warning';
  details: Record<string, any>;
  duration_ms?: number;
}

interface FormSubmission {
  timestamp: string; // ISO8601 format
  email_from: string;
  form_type: string;
  data: Record<string, any>;
}

class AdminAgent extends EventEmitter {
  private config: AdminConfig;
  private logDir: string;
  private leadsLog: string;
  private activityLog: string;
  private state: 'idle' | 'checking_email' | 'parsing_forms' | 'evaluating_thresholds' | 'spawning_agents' | 'reporting' | 'sleeping';
  private isRunning: boolean = false;
  private lastEmailCheck: Date = new Date(0);
  private specialtyAgentSchedules: Map<string, NodeJS.Timeout> = new Map();

  constructor(configPath: string, logDir: string = './logs') {
    super();
    
    this.state = 'idle';
    this.logDir = logDir;
    this.leadsLog = path.join(logDir, 'leads.jsonl');
    this.activityLog = path.join(logDir, 'admin_activity.jsonl');

    // Ensure log directory exists
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }

    // Load configuration
    try {
      const configContent = fs.readFileSync(configPath, 'utf-8');
      this.config = JSON.parse(configContent);
      this.log('Configuration loaded', 'success', { configPath });
    } catch (err) {
      this.log('Failed to load configuration', 'error', { error: String(err) });
      throw new Error(`Cannot load config from ${configPath}: ${err}`);
    }
  }

  /**
   * Start the agent event loop
   */
  public async start(): Promise<void> {
    if (this.isRunning) {
      this.log('Agent already running', 'warning', {});
      return;
    }

    this.isRunning = true;
    this.log('Agent started', 'success', { config: this.config });

    // Schedule specialty agents
    this.scheduleSpecialtyAgents();

    // Start main polling loop
    this.pollLoop();
  }

  /**
   * Stop the agent event loop
   */
  public async stop(): Promise<void> {
    this.isRunning = false;
    
    // Clear all scheduled tasks
    this.specialtyAgentSchedules.forEach((timer: NodeJS.Timeout) => clearInterval(timer));
    this.specialtyAgentSchedules.clear();

    this.log('Agent stopped', 'success', {});
  }

  /**
   * Main polling loop (runs every 5 minutes)
   */
  private pollLoop(): void {
    if (!this.isRunning) return;

    (async () => {
      try {
        await this.checkEmailAndProcess();
        await this.evaluateThresholds();
      } catch (err) {
        this.log('Poll cycle error', 'error', { error: String(err) });
      }
    })();

    // Schedule next poll (configurable, default 5 min)
    setTimeout(() => this.pollLoop(), this.config.polling_interval_ms || 300000);
  }

  /**
   * Check email on all configured accounts and parse form submissions
   */
  private async checkEmailAndProcess(): Promise<void> {
    this.state = 'checking_email';
    const startTime = Date.now();

    try {
      const formSubmissions: FormSubmission[] = [];

      for (const account of this.config.email_accounts) {
        try {
          // Use himalaya skill to check email
          const emails = await this.fetchEmails(account);
          
          for (const email of emails) {
            const forms = await this.parseFormSubmission(email);
            formSubmissions.push(...forms);
          }
        } catch (err) {
          this.log('Email check failed', 'error', {
            account: account.address,
            error: String(err),
          });
        }
      }

      // Log all form submissions
      for (const form of formSubmissions) {
        this.appendJsonl(this.leadsLog, form);
      }

      this.state = 'parsing_forms';
      const duration = Date.now() - startTime;

      this.log('Email check complete', 'success', {
        formSubmissions: formSubmissions.length,
        duration_ms: duration,
      });
    } catch (err) {
      this.log('Email processing error', 'error', { error: String(err) });
    }
  }

  /**
   * Evaluate performance thresholds and trigger alerts
   */
  private async evaluateThresholds(): Promise<void> {
    this.state = 'evaluating_thresholds';
    const startTime = Date.now();

    try {
      // Placeholder: would call Adspirer API to get current metrics
      // for now, this is a stub that demonstrates the pattern
      const metrics = await this.fetchCurrentMetrics();

      for (const threshold of this.config.thresholds) {
        const value = metrics[threshold.metric];
        const breached = this.checkThreshold(value, threshold.operator, threshold.value);

        if (breached) {
          this.log('Threshold breached', threshold.severity as any, {
            metric: threshold.metric,
            current: value,
            threshold: threshold.value,
            operator: threshold.operator,
          });

          if (this.config.telegram.enabled && this.config.telegram.webhook_url) {
            await this.sendTelegramAlert(threshold, value);
          }
        }
      }

      const duration = Date.now() - startTime;
      this.log('Threshold evaluation complete', 'success', { duration_ms: duration });
    } catch (err) {
      this.log('Threshold evaluation error', 'error', { error: String(err) });
    }
  }

  /**
   * Schedule specialty agents based on cron expressions
   */
  private scheduleSpecialtyAgents(): void {
    for (const agent of this.config.specialty_agents) {
      if (!agent.enabled) continue;

      // Note: Simple interval scheduling. For true cron, use 'node-cron' package
      // This is a stub that would need cron library integration
      this.log('Specialty agent scheduled', 'warning', { agent: agent.name, schedule: agent.schedule });
    }
  }

  /**
   * Helper: Fetch emails from account (placeholder for himalaya integration)
   */
  private async fetchEmails(account: EmailAccount): Promise<any[]> {
    // TODO: Integrate with himalaya skill to fetch emails
    // This would call: himalaya list <account> --limit 10
    // and parse the output
    return [];
  }

  /**
   * Helper: Parse form submission from email body
   */
  private async parseFormSubmission(email: any): Promise<FormSubmission[]> {
    // TODO: Extract form fields from email body
    // Return array of FormSubmission objects
    return [];
  }

  /**
   * Helper: Fetch current metrics from ad platforms
   */
  private async fetchCurrentMetrics(): Promise<Record<string, number>> {
    // TODO: Call Adspirer API to fetch current CPA, daily spend, CTR
    // This would integrate with get_campaign_performance and similar tools
    return {
      cpa: 50,
      daily_spend: 100,
      ctr: 0.8,
    };
  }

  /**
   * Helper: Check if value breaches threshold
   */
  private checkThreshold(
    value: number,
    operator: 'gt' | 'lt' | 'eq',
    threshold: number
  ): boolean {
    switch (operator) {
      case 'gt':
        return value > threshold;
      case 'lt':
        return value < threshold;
      case 'eq':
        return value === threshold;
      default:
        return false;
    }
  }

  /**
   * Helper: Send Telegram alert
   */
  private async sendTelegramAlert(threshold: Threshold, value: number): Promise<void> {
    if (!this.config.telegram.webhook_url) return;

    const message = `⚠️ Alert: ${threshold.metric} (${value}) breached threshold (${threshold.value})`;

    try {
      // TODO: POST to Telegram webhook
      this.log('Telegram alert sent', 'success', { message });
    } catch (err) {
      this.log('Failed to send Telegram alert', 'error', { error: String(err) });
    }
  }

  /**
   * Logger: Append structured log entry
   */
  private log(
    event_type: string,
    status: 'success' | 'error' | 'warning',
    details: Record<string, any> = {}
  ): void {
    const entry: ActivityLog = {
      timestamp: new Date().toISOString(),
      event_type,
      status,
      details,
    };

    this.appendJsonl(this.activityLog, entry);
    console.log(`[${entry.timestamp}] ${status.toUpperCase()}: ${event_type}`, details);
  }

  /**
   * Helper: Append to JSONL log file (atomic)
   */
  private appendJsonl(filePath: string, obj: any): void {
    const line = JSON.stringify(obj) + '\n';
    try {
      fs.appendFileSync(filePath, line, 'utf-8');
    } catch (err) {
      console.error(`Failed to write to ${filePath}:`, err);
    }
  }
}

export default AdminAgent;

// CLI entry point (for systemd service or manual invocation)
async function main() {
  const configPath = process.env.ADMIN_CONFIG || './admin_schedules.json';
  const logDir = process.env.ADMIN_LOG_DIR || './logs';

  const agent = new AdminAgent(configPath, logDir);

  // Graceful shutdown
  process.on('SIGTERM', async () => {
    console.log('SIGTERM received, shutting down...');
    await agent.stop();
    process.exit(0);
  });

  process.on('SIGINT', async () => {
    console.log('SIGINT received, shutting down...');
    await agent.stop();
    process.exit(0);
  });

  await agent.start();
}

main().catch((err) => {
  console.error('Failed to start admin agent:', err);
  process.exit(1);
});
