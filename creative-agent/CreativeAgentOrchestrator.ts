import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

/**
 * Creative Agent Orchestrator
 * 
 * Spawns CopyBot and ImageBot sub-agents in parallel,
 * collects outputs, validates creatives, and generates
 * a Creative Package manifest ready for Adspirer Agent
 */

export interface CampaignBrief {
  campaign_id: string;
  campaign_name: string;
  platform: "google_ads" | "meta_ads" | "linkedin_ads" | "tiktok_ads";
  business_name: string;
  business_description: string;
  target_audience: string;
  value_proposition: string;
  creative_requirements: {
    formats: string[];
    styles: string[];
    tone: string;
    themes: string[];
  };
  budget: {
    total: number;
    currency: string;
  };
  timeline: {
    start_date: string;
    end_date: string;
  };
}

export interface Creative {
  id: string;
  type: "headline" | "description" | "image";
  content: string;
  theme: string;
  char_count?: number;
  url?: string;
  format?: string;
  dimensions?: string;
}

export interface CreativePackage {
  brief_id: string;
  campaign_name: string;
  status: "ready" | "in_progress" | "blocked";
  timestamp: string;
  research_insights: {
    themes: string[];
    target_audience: string;
    key_messages: string[];
  };
  creatives: {
    headlines: Creative[];
    descriptions: Creative[];
    images: Creative[];
  };
  manifest: {
    total_assets: number;
    asset_counts: {
      headlines: number;
      descriptions: number;
      images: number;
    };
    platform_specs: {
      headline_max_length: number;
      description_max_length: number;
      image_dimensions: string[];
    };
    checksums: {
      headlines_hash: string;
      descriptions_hash: string;
      images_hash: string;
    };
    generated_at: string;
    version: string;
  };
  validation_report: {
    all_valid: boolean;
    errors: string[];
    warnings: string[];
  };
  upload_status: {
    uploaded: boolean;
    gcs_urls?: string[];
    upload_timestamp?: string;
  };
}

export class CreativeAgentOrchestrator {
  private workspaceDir: string;
  private checkpointDir: string;
  private platform: string;
  private platformSpecs: {
    [key: string]: {
      headline_max_length: number;
      description_max_length: number;
      image_dimensions: string[];
    };
  };

  constructor(workspaceDir = "/home/brad/.openclaw/workspace") {
    this.workspaceDir = workspaceDir;
    this.checkpointDir = path.join(workspaceDir, "creative_output");
    this.ensureDirectories();

    // Platform-specific constraints
    this.platformSpecs = {
      google_ads: {
        headline_max_length: 30,
        description_max_length: 90,
        image_dimensions: ["1200x628", "1200x1200"],
      },
      meta_ads: {
        headline_max_length: 125,
        description_max_length: 27,
        image_dimensions: ["1200x628", "1080x1080"],
      },
      linkedin_ads: {
        headline_max_length: 100,
        description_max_length: 300,
        image_dimensions: ["1200x627"],
      },
      tiktok_ads: {
        headline_max_length: 60,
        description_max_length: 150,
        image_dimensions: ["1080x1920", "1200x1200"],
      },
    };
  }

  private ensureDirectories(): void {
    [this.checkpointDir].forEach((dir) => {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    });
  }

  /**
   * Main orchestration method: spawn copybot and imagebot in parallel
   */
  async orchestrate(brief: CampaignBrief): Promise<CreativePackage> {
    const startTime = Date.now();
    this.log(`Starting orchestration for campaign: ${brief.campaign_name}`);

    try {
      // Initialize status
      this.saveCheckpoint(brief.campaign_id, { status: "in_progress", stage: "spawning" });

      // Spawn both agents in parallel
      this.log("Spawning CopyBot and ImageBot in parallel...");
      const [copyResults, imageResults] = await Promise.all([
        this.spawnCopyBot(brief),
        this.spawnImageBot(brief),
      ]);

      this.saveCheckpoint(brief.campaign_id, { status: "validating", stage: "spawning" });

      // Validate creatives
      this.log("Validating creative assets...");
      const validationReport = this.validateCreatives(copyResults, imageResults, brief.platform);

      if (!validationReport.all_valid) {
        this.log(`Validation failed with ${validationReport.errors.length} errors`, "error");
      }

      // Generate manifest
      this.log("Generating Creative Package manifest...");
      const creativePackage = this.generateManifest(
        brief,
        copyResults,
        imageResults,
        validationReport
      );

      // Save final checkpoint
      this.saveCheckpoint(brief.campaign_id, {
        status: "complete",
        stage: "manifest_generated",
        duration_ms: Date.now() - startTime,
      });

      this.log(
        `✅ Orchestration complete in ${Date.now() - startTime}ms for ${brief.campaign_name}`
      );
      return creativePackage;
    } catch (error) {
      this.log(`❌ Orchestration failed: ${error}`, "error");
      this.saveCheckpoint(brief.campaign_id, { status: "blocked", error: String(error) });
      throw error;
    }
  }

  /**
   * Spawn CopyBot sub-agent (simulated - uses existing copybot_output.json)
   */
  private async spawnCopyBot(brief: CampaignBrief): Promise<Creative[]> {
    this.log("CopyBot: Loading copy variants from checkpoint...");

    const copybotPath = path.join(this.workspaceDir, "copybot_output.json");
    if (!fs.existsSync(copybotPath)) {
      throw new Error(`CopyBot output not found at ${copybotPath}`);
    }

    const copyData = JSON.parse(fs.readFileSync(copybotPath, "utf-8"));
    const creatives: Creative[] = [];

    // Add headlines
    copyData.headlines.forEach((h: any) => {
      creatives.push({
        id: h.id,
        type: "headline",
        content: h.text,
        theme: h.theme,
        char_count: h.char_count,
      });
    });

    // Add descriptions
    copyData.descriptions.forEach((d: any) => {
      creatives.push({
        id: d.id,
        type: "description",
        content: d.text,
        theme: d.theme,
        char_count: d.char_count,
      });
    });

    this.log(`✅ CopyBot: Loaded ${copyData.headlines.length} headlines + ${copyData.descriptions.length} descriptions`);
    return creatives;
  }

  /**
   * Spawn ImageBot sub-agent (simulated - uses existing imagebot_output.json)
   */
  private async spawnImageBot(brief: CampaignBrief): Promise<Creative[]> {
    this.log("ImageBot: Loading image URLs from checkpoint...");

    const imagebotPath = path.join(this.workspaceDir, "imagebot_output.json");
    if (!fs.existsSync(imagebotPath)) {
      throw new Error(`ImageBot output not found at ${imagebotPath}`);
    }

    const imageData = JSON.parse(fs.readFileSync(imagebotPath, "utf-8"));
    const creatives: Creative[] = [];

    // Convert prompts to placeholder images (in real scenario, these would be actual URLs)
    const themes = imageData.prompts_prepared || {};
    Object.entries(themes).forEach(([theme, prompts]: [string, any]) => {
      if (Array.isArray(prompts)) {
        prompts.forEach((prompt, idx) => {
          creatives.push({
            id: `img_${theme.toLowerCase()}_${idx + 1}`,
            type: "image",
            content: prompt,
            theme: theme,
            url: `https://placeholder.com/1024x1024?text=${theme}+${idx + 1}`,
            format: "jpg",
            dimensions: "1024x1024",
          });
        });
      }
    });

    this.log(`✅ ImageBot: Loaded ${creatives.length} image placeholders from themes`);
    return creatives;
  }

  /**
   * Validate all creatives against platform specs
   */
  private validateCreatives(
    copyCreatives: Creative[],
    imageCreatives: Creative[],
    platform: string
  ): {
    all_valid: boolean;
    errors: string[];
    warnings: string[];
  } {
    const errors: string[] = [];
    const warnings: string[] = [];
    const specs = this.platformSpecs[platform] || this.platformSpecs.google_ads;

    // Validate copy
    copyCreatives.forEach((creative) => {
      if (creative.type === "headline" && creative.char_count) {
        if (creative.char_count > specs.headline_max_length) {
          errors.push(
            `Headline "${creative.id}" exceeds max length (${creative.char_count} > ${specs.headline_max_length})`
          );
        }
      } else if (creative.type === "description" && creative.char_count) {
        if (creative.char_count > specs.description_max_length) {
          errors.push(
            `Description "${creative.id}" exceeds max length (${creative.char_count} > ${specs.description_max_length})`
          );
        }
      }
    });

    // Validate images
    imageCreatives.forEach((creative) => {
      if (creative.type === "image") {
        if (!creative.url) {
          errors.push(`Image "${creative.id}" missing URL`);
        }
        if (!creative.dimensions) {
          warnings.push(`Image "${creative.id}" missing dimension metadata`);
        }
      }
    });

    return {
      all_valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Generate Creative Package manifest with checksums and metadata
   */
  private generateManifest(
    brief: CampaignBrief,
    copyCreatives: Creative[],
    imageCreatives: Creative[],
    validationReport: any
  ): CreativePackage {
    const headlines = copyCreatives.filter((c) => c.type === "headline");
    const descriptions = copyCreatives.filter((c) => c.type === "description");
    const images = imageCreatives.filter((c) => c.type === "image");

    const specs = this.platformSpecs[brief.platform] || this.platformSpecs.google_ads;

    const pkg: CreativePackage = {
      brief_id: brief.campaign_id,
      campaign_name: brief.campaign_name,
      status: validationReport.all_valid ? "ready" : "blocked",
      timestamp: new Date().toISOString(),
      research_insights: {
        themes: brief.creative_requirements.themes,
        target_audience: brief.target_audience,
        key_messages: [
          brief.value_proposition,
          ...brief.creative_requirements.themes,
        ],
      },
      creatives: {
        headlines: headlines,
        descriptions: descriptions,
        images: images,
      },
      manifest: {
        total_assets: headlines.length + descriptions.length + images.length,
        asset_counts: {
          headlines: headlines.length,
          descriptions: descriptions.length,
          images: images.length,
        },
        platform_specs: specs,
        checksums: {
          headlines_hash: this.generateChecksum(JSON.stringify(headlines)),
          descriptions_hash: this.generateChecksum(JSON.stringify(descriptions)),
          images_hash: this.generateChecksum(JSON.stringify(images)),
        },
        generated_at: new Date().toISOString(),
        version: "1.0.0",
      },
      validation_report: validationReport,
      upload_status: {
        uploaded: false,
      },
    };

    return pkg;
  }

  /**
   * Generate SHA256 checksum for asset integrity
   */
  private generateChecksum(data: string): string {
    return crypto.createHash("sha256").update(data).digest("hex");
  }

  /**
   * Save checkpoint for resumability
   */
  private saveCheckpoint(campaignId: string, data: any): void {
    const checkpointPath = path.join(this.checkpointDir, `${campaignId}_checkpoint.json`);
    const checkpoint = {
      timestamp: new Date().toISOString(),
      ...data,
    };
    fs.writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 2));
  }

  /**
   * Load checkpoint for resumability
   */
  private loadCheckpoint(campaignId: string): any | null {
    const checkpointPath = path.join(this.checkpointDir, `${campaignId}_checkpoint.json`);
    if (fs.existsSync(checkpointPath)) {
      return JSON.parse(fs.readFileSync(checkpointPath, "utf-8"));
    }
    return null;
  }

  /**
   * Logging utility
   */
  private log(message: string, level = "info"): void {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`);
  }

  /**
   * Export Creative Package to JSON file
   */
  async exportPackage(pkg: CreativePackage, filename?: string): Promise<string> {
    const finalPath = filename
      || path.join(this.checkpointDir, `${pkg.brief_id}_creative_package.json`);
    fs.writeFileSync(finalPath, JSON.stringify(pkg, null, 2));
    this.log(`✅ Creative Package exported to ${finalPath}`);
    return finalPath;
  }
}

// Exported class and types are already exported above
