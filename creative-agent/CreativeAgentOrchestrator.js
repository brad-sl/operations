"use strict";
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.CreativeAgentOrchestrator = void 0;
var fs = require("fs");
var path = require("path");
var crypto = require("crypto");
var CreativeAgentOrchestrator = /** @class */ (function () {
    function CreativeAgentOrchestrator(workspaceDir) {
        if (workspaceDir === void 0) { workspaceDir = "/home/brad/.openclaw/workspace"; }
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
    CreativeAgentOrchestrator.prototype.ensureDirectories = function () {
        [this.checkpointDir].forEach(function (dir) {
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
        });
    };
    /**
     * Main orchestration method: spawn copybot and imagebot in parallel
     */
    CreativeAgentOrchestrator.prototype.orchestrate = function (brief) {
        return __awaiter(this, void 0, void 0, function () {
            var startTime, _a, copyResults, imageResults, validationReport, creativePackage, error_1;
            return __generator(this, function (_b) {
                switch (_b.label) {
                    case 0:
                        startTime = Date.now();
                        this.log("Starting orchestration for campaign: ".concat(brief.campaign_name));
                        _b.label = 1;
                    case 1:
                        _b.trys.push([1, 3, , 4]);
                        // Initialize status
                        this.saveCheckpoint(brief.campaign_id, { status: "in_progress", stage: "spawning" });
                        // Spawn both agents in parallel
                        this.log("Spawning CopyBot and ImageBot in parallel...");
                        return [4 /*yield*/, Promise.all([
                                this.spawnCopyBot(brief),
                                this.spawnImageBot(brief),
                            ])];
                    case 2:
                        _a = _b.sent(), copyResults = _a[0], imageResults = _a[1];
                        this.saveCheckpoint(brief.campaign_id, { status: "validating", stage: "spawning" });
                        // Validate creatives
                        this.log("Validating creative assets...");
                        validationReport = this.validateCreatives(copyResults, imageResults, brief.platform);
                        if (!validationReport.all_valid) {
                            this.log("Validation failed with ".concat(validationReport.errors.length, " errors"), "error");
                        }
                        // Generate manifest
                        this.log("Generating Creative Package manifest...");
                        creativePackage = this.generateManifest(brief, copyResults, imageResults, validationReport);
                        // Save final checkpoint
                        this.saveCheckpoint(brief.campaign_id, {
                            status: "complete",
                            stage: "manifest_generated",
                            duration_ms: Date.now() - startTime,
                        });
                        this.log("\u2705 Orchestration complete in ".concat(Date.now() - startTime, "ms for ").concat(brief.campaign_name));
                        return [2 /*return*/, creativePackage];
                    case 3:
                        error_1 = _b.sent();
                        this.log("\u274C Orchestration failed: ".concat(error_1), "error");
                        this.saveCheckpoint(brief.campaign_id, { status: "blocked", error: String(error_1) });
                        throw error_1;
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    /**
     * Spawn CopyBot sub-agent (simulated - uses existing copybot_output.json)
     */
    CreativeAgentOrchestrator.prototype.spawnCopyBot = function (brief) {
        return __awaiter(this, void 0, void 0, function () {
            var copybotPath, copyData, creatives;
            return __generator(this, function (_a) {
                this.log("CopyBot: Loading copy variants from checkpoint...");
                copybotPath = path.join(this.workspaceDir, "copybot_output.json");
                if (!fs.existsSync(copybotPath)) {
                    throw new Error("CopyBot output not found at ".concat(copybotPath));
                }
                copyData = JSON.parse(fs.readFileSync(copybotPath, "utf-8"));
                creatives = [];
                // Add headlines
                copyData.headlines.forEach(function (h) {
                    creatives.push({
                        id: h.id,
                        type: "headline",
                        content: h.text,
                        theme: h.theme,
                        char_count: h.char_count,
                    });
                });
                // Add descriptions
                copyData.descriptions.forEach(function (d) {
                    creatives.push({
                        id: d.id,
                        type: "description",
                        content: d.text,
                        theme: d.theme,
                        char_count: d.char_count,
                    });
                });
                this.log("\u2705 CopyBot: Loaded ".concat(copyData.headlines.length, " headlines + ").concat(copyData.descriptions.length, " descriptions"));
                return [2 /*return*/, creatives];
            });
        });
    };
    /**
     * Spawn ImageBot sub-agent (simulated - uses existing imagebot_output.json)
     */
    CreativeAgentOrchestrator.prototype.spawnImageBot = function (brief) {
        return __awaiter(this, void 0, void 0, function () {
            var imagebotPath, imageData, creatives, themes;
            return __generator(this, function (_a) {
                this.log("ImageBot: Loading image URLs from checkpoint...");
                imagebotPath = path.join(this.workspaceDir, "imagebot_output.json");
                if (!fs.existsSync(imagebotPath)) {
                    throw new Error("ImageBot output not found at ".concat(imagebotPath));
                }
                imageData = JSON.parse(fs.readFileSync(imagebotPath, "utf-8"));
                creatives = [];
                themes = imageData.prompts_prepared || {};
                Object.entries(themes).forEach(function (_a) {
                    var theme = _a[0], prompts = _a[1];
                    if (Array.isArray(prompts)) {
                        prompts.forEach(function (prompt, idx) {
                            creatives.push({
                                id: "img_".concat(theme.toLowerCase(), "_").concat(idx + 1),
                                type: "image",
                                content: prompt,
                                theme: theme,
                                url: "https://placeholder.com/1024x1024?text=".concat(theme, "+").concat(idx + 1),
                                format: "jpg",
                                dimensions: "1024x1024",
                            });
                        });
                    }
                });
                this.log("\u2705 ImageBot: Loaded ".concat(creatives.length, " image placeholders from themes"));
                return [2 /*return*/, creatives];
            });
        });
    };
    /**
     * Validate all creatives against platform specs
     */
    CreativeAgentOrchestrator.prototype.validateCreatives = function (copyCreatives, imageCreatives, platform) {
        var errors = [];
        var warnings = [];
        var specs = this.platformSpecs[platform] || this.platformSpecs.google_ads;
        // Validate copy
        copyCreatives.forEach(function (creative) {
            if (creative.type === "headline" && creative.char_count) {
                if (creative.char_count > specs.headline_max_length) {
                    errors.push("Headline \"".concat(creative.id, "\" exceeds max length (").concat(creative.char_count, " > ").concat(specs.headline_max_length, ")"));
                }
            }
            else if (creative.type === "description" && creative.char_count) {
                if (creative.char_count > specs.description_max_length) {
                    errors.push("Description \"".concat(creative.id, "\" exceeds max length (").concat(creative.char_count, " > ").concat(specs.description_max_length, ")"));
                }
            }
        });
        // Validate images
        imageCreatives.forEach(function (creative) {
            if (creative.type === "image") {
                if (!creative.url) {
                    errors.push("Image \"".concat(creative.id, "\" missing URL"));
                }
                if (!creative.dimensions) {
                    warnings.push("Image \"".concat(creative.id, "\" missing dimension metadata"));
                }
            }
        });
        return {
            all_valid: errors.length === 0,
            errors: errors,
            warnings: warnings,
        };
    };
    /**
     * Generate Creative Package manifest with checksums and metadata
     */
    CreativeAgentOrchestrator.prototype.generateManifest = function (brief, copyCreatives, imageCreatives, validationReport) {
        var headlines = copyCreatives.filter(function (c) { return c.type === "headline"; });
        var descriptions = copyCreatives.filter(function (c) { return c.type === "description"; });
        var images = imageCreatives.filter(function (c) { return c.type === "image"; });
        var specs = this.platformSpecs[brief.platform] || this.platformSpecs.google_ads;
        var pkg = {
            brief_id: brief.campaign_id,
            campaign_name: brief.campaign_name,
            status: validationReport.all_valid ? "ready" : "blocked",
            timestamp: new Date().toISOString(),
            research_insights: {
                themes: brief.creative_requirements.themes,
                target_audience: brief.target_audience,
                key_messages: __spreadArray([
                    brief.value_proposition
                ], brief.creative_requirements.themes, true),
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
    };
    /**
     * Generate SHA256 checksum for asset integrity
     */
    CreativeAgentOrchestrator.prototype.generateChecksum = function (data) {
        return crypto.createHash("sha256").update(data).digest("hex");
    };
    /**
     * Save checkpoint for resumability
     */
    CreativeAgentOrchestrator.prototype.saveCheckpoint = function (campaignId, data) {
        var checkpointPath = path.join(this.checkpointDir, "".concat(campaignId, "_checkpoint.json"));
        var checkpoint = __assign({ timestamp: new Date().toISOString() }, data);
        fs.writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 2));
    };
    /**
     * Load checkpoint for resumability
     */
    CreativeAgentOrchestrator.prototype.loadCheckpoint = function (campaignId) {
        var checkpointPath = path.join(this.checkpointDir, "".concat(campaignId, "_checkpoint.json"));
        if (fs.existsSync(checkpointPath)) {
            return JSON.parse(fs.readFileSync(checkpointPath, "utf-8"));
        }
        return null;
    };
    /**
     * Logging utility
     */
    CreativeAgentOrchestrator.prototype.log = function (message, level) {
        if (level === void 0) { level = "info"; }
        var timestamp = new Date().toISOString();
        console.log("[".concat(timestamp, "] [").concat(level.toUpperCase(), "] ").concat(message));
    };
    /**
     * Export Creative Package to JSON file
     */
    CreativeAgentOrchestrator.prototype.exportPackage = function (pkg, filename) {
        return __awaiter(this, void 0, void 0, function () {
            var finalPath;
            return __generator(this, function (_a) {
                finalPath = filename
                    || path.join(this.checkpointDir, "".concat(pkg.brief_id, "_creative_package.json"));
                fs.writeFileSync(finalPath, JSON.stringify(pkg, null, 2));
                this.log("\u2705 Creative Package exported to ".concat(finalPath));
                return [2 /*return*/, finalPath];
            });
        });
    };
    return CreativeAgentOrchestrator;
}());
exports.CreativeAgentOrchestrator = CreativeAgentOrchestrator;
// Exported class and types are already exported above
