// Synthetic Settings/Jobs fixtures for the installed #59 scenario. Pure: the
// builder returns text and the validators read text; writing is the caller's
// job and only after FixtureWritePolicy confirms OFFLINE. Mirrors product HEAD
// 890364e: backend/src/domain/models.py (JobModel), backend/src/services/
// settings.py (RuntimeSettings, extra="forbid") and frontend/src-tauri/src/
// recovery.rs (confirm_saved_idle). Fixtures are past synthetic terminal
// history only: no media, no real transcription result, no user data.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Qa59Installed
{
    public enum FixtureClass
    {
        TERMINAL_IDLE, ACTIVE_JOB, UNKNOWN_JOB_ENUM, ACTIVE_DRIVE, UNKNOWN_DRIVE_ENUM,
        MALFORMED, MISSING,
        // Input our strict reader refuses but serde_json might accept
        // (duplicate keys, huge integers): never usable as a fixture.
        AMBIGUOUS,
    }

    public enum NegativeFixture
    {
        ACTIVE_JOB_WAITING, ACTIVE_JOB_TRANSCRIBING, ACTIVE_FILE_CANCEL_REQUESTED,
        ACTIVE_DRIVE_PENDING, ACTIVE_DRIVE_UPLOADING,
        UNKNOWN_JOB_ENUM, UNKNOWN_FILE_ENUM, UNKNOWN_DRIVE_ENUM,
        CORRUPT_TRUNCATED,
    }

    public static class SyntheticFixtures
    {
        public const string RootPrefix = "qa59-fixture-";
        public const string DriveExamRootDefault = "2026 제37회 공인중개사 자격시험";
        public const string UnknownEnum = "QA59_UNKNOWN_STATE";

        public static readonly string[] FileStatuses =
        {
            "WAITING", "PREPARING", "TRANSCRIBING", "SAVING", "VERIFYING", "DONE",
            "FAILED", "STOPPED", "CANCELLED", "CRASHED", "CANCEL_REQUESTED",
        };
        public static readonly string[] DriveStatuses =
        {
            "DISABLED", "AUTH_REQUIRED", "CLASSIFICATION_FAILED", "PENDING", "UPLOADING", "DONE", "FAILED",
        };
        // recovery.rs confirm_saved_idle terminal sets.
        public static readonly string[] TerminalFileStatuses = { "DONE", "FAILED", "STOPPED", "CANCELLED", "CRASHED" };
        public static readonly string[] IdleDriveStatuses = { "DISABLED", "AUTH_REQUIRED", "CLASSIFICATION_FAILED", "DONE", "FAILED" };

        public static readonly string[] SettingsKeys =
        {
            "notifications", "close_behavior", "shutdown", "transcription_folder", "last_course",
            "last_subject", "last_engine", "subject_stage_overrides", "drive_exam_root",
        };
        public static readonly string[] JobKeys =
        {
            "job_id", "created_at", "updated_at", "status", "folder", "engine", "engine_config",
            "force_retranscribe", "upload_to_drive", "total_files", "done_files", "failed_files",
            "current_file", "current_progress", "eta_seconds", "files", "events", "drive", "error",
            "course", "subject", "stage", "file_metadata", "batch_completed",
        };
        private static readonly string[] EventKeys = { "timestamp", "level", "category", "message", "file_id", "filename" };
        private static readonly string[] DriveKeys = { "status", "error", "remote_file_ids", "updated_at" };
        private static readonly string[] MetadataKeys = { "week", "lesson", "normalized_name" };
        private static readonly string[] BannedSegments = { "sorigul", "전사", "desktop", "onedrive", "documents", ".credentials" };
        private static readonly string[] ForbiddenContent =
        {
            ".mp3", ".m4a", ".wav", ".mp4", ".aac", ".flac", ".ogg", ".webm", ".wma",
            "token", "secret", "credential", "password", "client_id",
        };

        // Distinct per revision so the UI summary proves which Jobs state it shows:
        // A = 2 total / 1 done / 1 failed, B = 3 total / 1 done / 2 failed.
        public static long TotalFiles(char revision) { return revision == 'A' ? 2 : 3; }
        public static long DoneFiles(char revision) { return 1; }
        public static long FailedFiles(char revision) { return revision == 'A' ? 1 : 2; }

        public static string JobId(char revision) { return revision == 'A' ? "00000000-0000-4000-8000-00000000000a" : "00000000-0000-4000-8000-00000000000b"; }
        public static string Timestamp(char revision) { return revision == 'A' ? "2026-01-01T00:00:00" : "2026-01-02T00:00:00"; }
        public static string FolderFor(string root, char revision) { return root + "\\revision-" + revision; }

        private static void RequireRevision(char revision)
        {
            if (revision != 'A' && revision != 'B') throw new ArgumentException("FIXTURE_REVISION");
        }

        // ---- builders -------------------------------------------------------

        public static string SettingsJson(string root, char revision)
        {
            RequireRevision(revision);
            var notifications = new JsonObject();
            // Off: no completion toasts competing with the main window.
            notifications.TryAdd("file_complete", false);
            notifications.TryAdd("job_complete", false);
            var s = new JsonObject();
            s.TryAdd("notifications", notifications);
            s.TryAdd("close_behavior", "exit");
            s.TryAdd("shutdown", "disabled");
            s.TryAdd("transcription_folder", FolderFor(root, revision));
            s.TryAdd("last_course", JsonNull.Value);
            s.TryAdd("last_subject", JsonNull.Value);
            s.TryAdd("last_engine", "local_whisper");
            s.TryAdd("subject_stage_overrides", new JsonObject());
            s.TryAdd("drive_exam_root", DriveExamRootDefault);
            return JsonText.Write(s);
        }

        public static string JobsJson(string root, char revision)
        {
            RequireRevision(revision);
            var jobs = new JsonObject();
            jobs.TryAdd(JobId(revision), TerminalJob(root, revision));
            return JsonText.Write(jobs);
        }

        // Negative fixtures reuse revision A and change only the field under test.
        public static string NegativeJobsJson(string root, NegativeFixture kind)
        {
            if (kind == NegativeFixture.CORRUPT_TRUNCATED)
            {
                string full = JobsJson(root, 'A');
                return full.Substring(0, full.Length / 2);
            }
            JsonObject job = TerminalJob(root, 'A');
            JsonObject files = (JsonObject)job.Get("files");
            string firstFile = files.Keys[0];
            switch (kind)
            {
                case NegativeFixture.ACTIVE_JOB_WAITING: job.Replace("status", "WAITING"); break;
                case NegativeFixture.ACTIVE_JOB_TRANSCRIBING: job.Replace("status", "TRANSCRIBING"); break;
                case NegativeFixture.ACTIVE_FILE_CANCEL_REQUESTED: files.Replace(firstFile, "CANCEL_REQUESTED"); break;
                case NegativeFixture.UNKNOWN_JOB_ENUM: job.Replace("status", UnknownEnum); break;
                case NegativeFixture.UNKNOWN_FILE_ENUM: files.Replace(firstFile, UnknownEnum); break;
                case NegativeFixture.ACTIVE_DRIVE_PENDING:
                case NegativeFixture.ACTIVE_DRIVE_UPLOADING:
                case NegativeFixture.UNKNOWN_DRIVE_ENUM:
                    string status = kind == NegativeFixture.ACTIVE_DRIVE_PENDING ? "PENDING"
                        : kind == NegativeFixture.ACTIVE_DRIVE_UPLOADING ? "UPLOADING" : UnknownEnum;
                    var state = new JsonObject();
                    state.TryAdd("status", status);
                    state.TryAdd("error", JsonNull.Value);
                    state.TryAdd("remote_file_ids", new JsonObject());
                    state.TryAdd("updated_at", Timestamp('A'));
                    var drive = new JsonObject();
                    drive.TryAdd(firstFile, state);
                    job.Replace("upload_to_drive", true);
                    job.Replace("drive", drive);
                    break;
                default: throw new ArgumentException("FIXTURE_NEGATIVE_KIND");
            }
            var jobs = new JsonObject();
            jobs.TryAdd(JobId('A'), job);
            return JsonText.Write(jobs);
        }

        private static JsonObject TerminalJob(string root, char revision)
        {
            var files = new JsonObject();
            long total = TotalFiles(revision);
            for (long n = 1; n <= total; n++)
            {
                files.TryAdd("qa59-synthetic-" + char.ToLowerInvariant(revision) + "-" + n.ToString(CultureInfo.InvariantCulture),
                    n <= DoneFiles(revision) ? "DONE" : "FAILED");
            }
            var job = new JsonObject();
            job.TryAdd("job_id", JobId(revision));
            job.TryAdd("created_at", Timestamp(revision));
            job.TryAdd("updated_at", Timestamp(revision));
            job.TryAdd("status", "FAILED");
            job.TryAdd("folder", FolderFor(root, revision));
            job.TryAdd("engine", "local_whisper");
            job.TryAdd("engine_config", new JsonObject());
            job.TryAdd("force_retranscribe", false);
            job.TryAdd("upload_to_drive", false);
            job.TryAdd("total_files", total);
            job.TryAdd("done_files", DoneFiles(revision));
            job.TryAdd("failed_files", FailedFiles(revision));
            job.TryAdd("current_file", JsonNull.Value);
            job.TryAdd("current_progress", JsonNull.Value);
            job.TryAdd("eta_seconds", JsonNull.Value);
            job.TryAdd("files", files);
            job.TryAdd("events", new List<object>());
            job.TryAdd("drive", new JsonObject());
            job.TryAdd("error", JsonNull.Value);
            job.TryAdd("course", JsonNull.Value);
            job.TryAdd("subject", JsonNull.Value);
            job.TryAdd("stage", JsonNull.Value);
            job.TryAdd("file_metadata", new JsonObject());
            job.TryAdd("batch_completed", true);
            return job;
        }

        // ---- validators -----------------------------------------------------

        public static Outcome ValidateRoot(string root, IList<string> protectedRoots)
        {
            var outcome = new Outcome();
            if (root == null || root.Length < 4 || root.Length > 200) { outcome.Add("FIXTURE_ROOT_FORMAT"); return outcome; }
            char drive = root[0];
            if (!((drive >= 'A' && drive <= 'Z') || (drive >= 'a' && drive <= 'z')) || root[1] != ':' || root[2] != '\\'
                || root.IndexOf('/') >= 0 || root.IndexOfAny(new[] { '*', '?', '"', '<', '>', '|' }) >= 0
                || root.IndexOf(':', 2) >= 0 || root.EndsWith("\\", StringComparison.Ordinal))
            {
                outcome.Add("FIXTURE_ROOT_FORMAT");
                return outcome;
            }
            string[] segments = root.Substring(3).Split('\\');
            foreach (string segment in segments)
            {
                if (segment.Length == 0 || segment == "." || segment == ".." || segment.Trim() != segment || segment.EndsWith(".", StringComparison.Ordinal))
                    outcome.Add("FIXTURE_ROOT_FORMAT");
                foreach (string banned in BannedSegments)
                {
                    if (string.Equals(segment, banned, StringComparison.OrdinalIgnoreCase)) outcome.Add("FIXTURE_ROOT_PROTECTED");
                }
            }
            string last = segments[segments.Length - 1];
            if (!last.StartsWith(RootPrefix, StringComparison.Ordinal) || !Fields.IsLowerHex(last.Substring(RootPrefix.Length), 32))
                outcome.Add("FIXTURE_ROOT_NOT_RUNNER_OWNED");
            if (protectedRoots == null) { outcome.Add("FIXTURE_PROTECTED_ROOTS_UNKNOWN"); return outcome; }
            foreach (string p in protectedRoots)
            {
                if (string.IsNullOrEmpty(p)) { outcome.Add("FIXTURE_PROTECTED_ROOTS_UNKNOWN"); continue; }
                string prot = p.TrimEnd('\\');
                // Neither inside a protected root nor an ancestor of one.
                if (string.Equals(root, prot, StringComparison.OrdinalIgnoreCase)
                    || root.StartsWith(prot + "\\", StringComparison.OrdinalIgnoreCase)
                    || prot.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase))
                    outcome.Add("FIXTURE_ROOT_PROTECTED");
            }
            return outcome;
        }

        public static Outcome ValidateSettings(string text, string root, char revision, IList<string> protectedRoots)
        {
            Outcome outcome = ValidateRoot(root, protectedRoots);
            JsonObject s = Fields.ParseObject(text, outcome);
            if (s == null || !Fields.ExactKeys(s, SettingsKeys, outcome, "SETTINGS_")) return outcome;
            ForbiddenStrings(s, outcome);

            var n = s.Get("notifications") as JsonObject;
            if (n == null || !Fields.ExactKeys(n, new[] { "file_complete", "job_complete" }, outcome, "SETTINGS_NOTIFICATIONS_")
                || !(n.Get("file_complete") is bool) || !(n.Get("job_complete") is bool))
                outcome.Add("SETTINGS_NOTIFICATIONS_INVALID");
            if (!"tray".Equals(s.Get("close_behavior")) && !"exit".Equals(s.Get("close_behavior"))) outcome.Add("SETTINGS_CLOSE_BEHAVIOR_INVALID");
            // Shutdown must stay disabled: an armed Windows shutdown is never synthetic.
            if (!"disabled".Equals(s.Get("shutdown"))) outcome.Add("SETTINGS_SHUTDOWN_NOT_DISABLED");
            if (!StringOrNull(s.Get("last_course")) || !StringOrNull(s.Get("last_subject"))) outcome.Add("SETTINGS_TYPE");
            if (!"local_whisper".Equals(s.Get("last_engine")) && !"direct_colab".Equals(s.Get("last_engine"))) outcome.Add("SETTINGS_ENGINE_INVALID");
            var overrides = s.Get("subject_stage_overrides") as JsonObject;
            if (overrides == null) outcome.Add("SETTINGS_TYPE");
            else foreach (string key in overrides.Keys)
            {
                if (!"1차".Equals(overrides.Get(key)) && !"2차".Equals(overrides.Get(key))) outcome.Add("SETTINGS_STAGE_INVALID");
            }
            if (!(s.Get("drive_exam_root") is string)) outcome.Add("SETTINGS_TYPE");

            if (outcome.Ok && (revision == 'A' || revision == 'B'))
            {
                if (!FolderFor(root, revision).Equals(s.Get("transcription_folder"))) outcome.Add("FIXTURE_FOLDER_MISMATCH");
                if (!JsonText.DeepEquals(s, StrictJson.Parse(SettingsJson(root, revision)))) outcome.Add("FIXTURE_NOT_CANONICAL");
            }
            else if (revision != 'A' && revision != 'B') outcome.Add("FIXTURE_REVISION");
            return outcome;
        }

        // Terminal idle history A or B: full JobModel schema, consistent counts,
        // folder bound to the revision, Drive off, then canonical equality.
        public static Outcome ValidateJobs(string text, string root, char revision, IList<string> protectedRoots)
        {
            Outcome outcome = ValidateRoot(root, protectedRoots);
            if (revision != 'A' && revision != 'B') { outcome.Add("FIXTURE_REVISION"); return outcome; }
            JsonObject jobs = Fields.ParseObject(text, outcome);
            if (jobs == null) return outcome;
            ForbiddenStrings(jobs, outcome);
            if (jobs.Count != 1 || !jobs.Has(JobId(revision))) { outcome.Add("FIXTURE_JOB_SET"); return outcome; }
            var job = jobs.Get(JobId(revision)) as JsonObject;
            if (job == null || !ValidateJobModel(job, outcome)) return outcome;

            if (!JobId(revision).Equals(job.Get("job_id"))) outcome.Add("FIXTURE_JOB_ID");
            if (!FolderFor(root, revision).Equals(job.Get("folder"))) outcome.Add("FIXTURE_FOLDER_MISMATCH");
            if (Classify(text) != FixtureClass.TERMINAL_IDLE) outcome.Add("FIXTURE_NOT_TERMINAL");
            if (!false.Equals(job.Get("upload_to_drive")) || ((JsonObject)job.Get("drive")).Count != 0) outcome.Add("FIXTURE_DRIVE_ENABLED");

            var files = (JsonObject)job.Get("files");
            long total = (long)job.Get("total_files"), done = (long)job.Get("done_files"), failed = (long)job.Get("failed_files");
            long doneSeen = 0, failedSeen = 0;
            foreach (string key in files.Keys)
            {
                if ("DONE".Equals(files.Get(key))) doneSeen++;
                else if ("FAILED".Equals(files.Get(key))) failedSeen++;
            }
            if (files.Count != total || doneSeen != done || failedSeen != failed || done + failed != total)
                outcome.Add("FIXTURE_COUNTS_INCONSISTENT");
            if (!(failed > 0 ? "FAILED" : "DONE").Equals(job.Get("status"))) outcome.Add("FIXTURE_STATUS_INCONSISTENT");
            if (total != TotalFiles(revision) || done != DoneFiles(revision) || failed != FailedFiles(revision))
                outcome.Add("FIXTURE_REVISION_COUNTS");
            if (!true.Equals(job.Get("batch_completed"))) outcome.Add("FIXTURE_NOT_COMPLETED");

            if (outcome.Ok && !JsonText.DeepEquals(jobs, StrictJson.Parse(JobsJson(root, revision)))) outcome.Add("FIXTURE_NOT_CANONICAL");
            return outcome;
        }

        public static bool ValidateJobModel(JsonObject job, Outcome outcome)
        {
            if (!Fields.ExactKeys(job, JobKeys, outcome, "JOB_")) return false;
            int before = outcome.Reasons.Count;
            if (!(job.Get("job_id") is string) || !(job.Get("folder") is string) || !(job.Get("engine") is string)) outcome.Add("JOB_TYPE");
            if (!IsTimestamp(job.Get("created_at")) || !IsTimestamp(job.Get("updated_at"))) outcome.Add("JOB_TIMESTAMP");
            if (!IsEnum(job.Get("status"), FileStatuses)) outcome.Add("JOB_STATUS_ENUM");
            if (!(job.Get("engine_config") is JsonObject)) outcome.Add("JOB_TYPE");
            if (!(job.Get("force_retranscribe") is bool) || !(job.Get("upload_to_drive") is bool) || !(job.Get("batch_completed") is bool)) outcome.Add("JOB_TYPE");
            foreach (string key in new[] { "total_files", "done_files", "failed_files" })
            {
                if (!(job.Get(key) is long) || (long)job.Get(key) < 0) outcome.Add("JOB_COUNT");
            }
            if (!StringOrNull(job.Get("current_file")) || !StringOrNull(job.Get("error"))
                || !StringOrNull(job.Get("course")) || !StringOrNull(job.Get("subject"))) outcome.Add("JOB_TYPE");
            if (!NumberOrNull(job.Get("current_progress")) || !NumberOrNull(job.Get("eta_seconds"))) outcome.Add("JOB_TYPE");
            object stage = job.Get("stage");
            if (!(stage is JsonNull) && !"1차".Equals(stage) && !"2차".Equals(stage)) outcome.Add("JOB_STAGE_INVALID");

            var files = job.Get("files") as JsonObject;
            if (files == null) outcome.Add("JOB_TYPE");
            else foreach (string key in files.Keys)
            {
                if (!IsEnum(files.Get(key), FileStatuses)) outcome.Add("JOB_FILE_STATUS_ENUM");
            }
            var events = job.Get("events") as List<object>;
            if (events == null) outcome.Add("JOB_TYPE");
            else foreach (object item in events)
            {
                var e = item as JsonObject;
                if (e == null || !Fields.ExactKeys(e, EventKeys, outcome, "JOB_EVENT_") || !IsTimestamp(e.Get("timestamp"))
                    || !(e.Get("level") is string) || !(e.Get("category") is string) || !(e.Get("message") is string)
                    || !StringOrNull(e.Get("file_id")) || !StringOrNull(e.Get("filename")))
                    outcome.Add("JOB_EVENT_INVALID");
            }
            var drive = job.Get("drive") as JsonObject;
            if (drive == null) outcome.Add("JOB_TYPE");
            else foreach (string key in drive.Keys)
            {
                var d = drive.Get(key) as JsonObject;
                if (d == null || !Fields.ExactKeys(d, DriveKeys, outcome, "JOB_DRIVE_") || !IsEnum(d.Get("status"), DriveStatuses)
                    || !StringOrNull(d.Get("error")) || !(d.Get("remote_file_ids") is JsonObject) || !IsTimestamp(d.Get("updated_at")))
                    outcome.Add("JOB_DRIVE_INVALID");
            }
            var metadata = job.Get("file_metadata") as JsonObject;
            if (metadata == null) outcome.Add("JOB_TYPE");
            else foreach (string key in metadata.Keys)
            {
                var m = metadata.Get(key) as JsonObject;
                if (m == null || !Fields.ExactKeys(m, MetadataKeys, outcome, "JOB_METADATA_")
                    || !StringOrNull(m.Get("week")) || !StringOrNull(m.Get("lesson")) || !StringOrNull(m.Get("normalized_name")))
                    outcome.Add("JOB_METADATA_INVALID");
            }
            return outcome.Reasons.Count == before;
        }

        // Same decision order as recovery.rs: the whole file must deserialize
        // (status string + files map of strings + optional drive map of
        // {status string}) before any job is judged; then jobs in key order,
        // job/file states before Drive. null text = file absent.
        public static FixtureClass Classify(string text)
        {
            if (text == null) return FixtureClass.MISSING;
            JsonObject jobs;
            try
            {
                jobs = StrictJson.Parse(text) as JsonObject;
            }
            catch (JsonFormatException e)
            {
                return e.Code == "JSON_DUPLICATE_KEY" || e.Code == "JSON_INTEGER_OUT_OF_RANGE" || e.Code == "JSON_TOO_DEEP"
                    ? FixtureClass.AMBIGUOUS : FixtureClass.MALFORMED;
            }
            if (jobs == null) return FixtureClass.MALFORMED;
            foreach (string key in jobs.Keys)
            {
                var job = jobs.Get(key) as JsonObject;
                if (job == null || !(job.Get("status") is string) || !(job.Get("files") is JsonObject)) return FixtureClass.MALFORMED;
                var files = (JsonObject)job.Get("files");
                foreach (string f in files.Keys)
                {
                    if (!(files.Get(f) is string)) return FixtureClass.MALFORMED;
                }
                object drive = job.Get("drive");
                if (drive == null) continue;
                var driveMap = drive as JsonObject;
                if (driveMap == null) return FixtureClass.MALFORMED;
                foreach (string f in driveMap.Keys)
                {
                    var d = driveMap.Get(f) as JsonObject;
                    if (d == null || !(d.Get("status") is string)) return FixtureClass.MALFORMED;
                }
            }
            // BTreeMap<String,_> iterates in byte order; ordinal equals it for non-surrogate keys.
            var keys = new List<string>(jobs.Keys);
            keys.Sort(StringComparer.Ordinal);
            foreach (string key in keys)
            {
                var job = (JsonObject)jobs.Get(key);
                var files = (JsonObject)job.Get("files");
                var states = new List<string> { (string)job.Get("status") };
                foreach (string f in files.Keys) states.Add((string)files.Get(f));
                foreach (string state in states)
                {
                    if (Array.IndexOf(TerminalFileStatuses, state) < 0)
                        return IsAnyActive(states) ? FixtureClass.ACTIVE_JOB : FixtureClass.UNKNOWN_JOB_ENUM;
                }
                var driveMap = job.Get("drive") as JsonObject;
                if (driveMap == null) continue;
                var driveStates = new List<string>();
                foreach (string f in driveMap.Keys) driveStates.Add((string)((JsonObject)driveMap.Get(f)).Get("status"));
                foreach (string state in driveStates)
                {
                    if (Array.IndexOf(IdleDriveStatuses, state) < 0)
                    {
                        foreach (string s in driveStates)
                        {
                            if (Array.IndexOf(IdleDriveStatuses, s) < 0 && Array.IndexOf(DriveStatuses, s) >= 0) return FixtureClass.ACTIVE_DRIVE;
                        }
                        return FixtureClass.UNKNOWN_DRIVE_ENUM;
                    }
                }
            }
            return FixtureClass.TERMINAL_IDLE;
        }

        private static bool IsAnyActive(List<string> states)
        {
            foreach (string s in states)
            {
                if (Array.IndexOf(TerminalFileStatuses, s) < 0 && Array.IndexOf(FileStatuses, s) >= 0) return true;
            }
            return false;
        }

        // Product error code the restart/exit gate must show for this fixture.
        // null = idle (restart permitted). AMBIGUOUS has no defined expectation.
        public static string ExpectedProductCode(FixtureClass fixture)
        {
            switch (fixture)
            {
                case FixtureClass.TERMINAL_IDLE: return null;
                case FixtureClass.ACTIVE_JOB:
                case FixtureClass.UNKNOWN_JOB_ENUM: return "ACTIVE_OR_UNKNOWN_JOB";
                case FixtureClass.ACTIVE_DRIVE:
                case FixtureClass.UNKNOWN_DRIVE_ENUM: return "ACTIVE_OR_UNKNOWN_DRIVE";
                case FixtureClass.MALFORMED:
                case FixtureClass.MISSING: return "JOB_STATE_UNKNOWN";
                default: throw new ArgumentException("FIXTURE_AMBIGUOUS_HAS_NO_EXPECTATION");
            }
        }

        private static void ForbiddenStrings(JsonObject root, Outcome outcome)
        {
            foreach (string value in Fields.Strings(root))
            {
                string lower = value.ToLowerInvariant();
                foreach (string bad in ForbiddenContent)
                {
                    if (lower.Contains(bad)) { outcome.Add("FIXTURE_FORBIDDEN_CONTENT"); return; }
                }
            }
        }

        private static bool StringOrNull(object value) { return value is string || value is JsonNull; }
        private static bool NumberOrNull(object value) { return value is long || value is double || value is JsonNull; }
        private static bool IsEnum(object value, string[] allowed) { var s = value as string; return s != null && Array.IndexOf(allowed, s) >= 0; }

        private static bool IsTimestamp(object value)
        {
            var text = value as string;
            DateTime parsed;
            return text != null && DateTime.TryParseExact(text, new[] { "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss.ffffff" },
                CultureInfo.InvariantCulture, DateTimeStyles.None, out parsed);
        }
    }

    public static class FixtureWritePolicy
    {
        public const string OfflineConfirmed = "OFFLINE_CONFIRMED";

        // Replace saved Settings/Jobs only while the Backend is confirmed
        // stopped; ONLINE, unknown or "probably offline" never qualifies.
        public static bool MayReplace(string observedBackendState)
        {
            return string.Equals(observedBackendState, OfflineConfirmed, StringComparison.Ordinal);
        }
    }

    // Python json.dumps(indent=2, ensure_ascii=False) layout for builder output.
    public static class JsonText
    {
        public static string Write(object value)
        {
            var sb = new StringBuilder();
            Write(sb, value, 0);
            return sb.ToString();
        }

        private static void Write(StringBuilder sb, object value, int indent)
        {
            if (value is JsonNull) { sb.Append("null"); return; }
            if (value is bool) { sb.Append((bool)value ? "true" : "false"); return; }
            if (value is long) { sb.Append(((long)value).ToString(CultureInfo.InvariantCulture)); return; }
            if (value is double)
            {
                string real = ((double)value).ToString("R", CultureInfo.InvariantCulture);
                sb.Append(real.IndexOfAny(new[] { '.', 'E' }) >= 0 ? real : real + ".0");
                return;
            }
            var text = value as string;
            if (text != null) { WriteString(sb, text); return; }
            var obj = value as JsonObject;
            if (obj != null)
            {
                if (obj.Count == 0) { sb.Append("{}"); return; }
                sb.Append("{\n");
                for (int k = 0; k < obj.Count; k++)
                {
                    sb.Append(' ', indent + 2);
                    WriteString(sb, obj.Keys[k]);
                    sb.Append(": ");
                    Write(sb, obj.Get(obj.Keys[k]), indent + 2);
                    sb.Append(k + 1 < obj.Count ? ",\n" : "\n");
                }
                sb.Append(' ', indent).Append('}');
                return;
            }
            var list = value as List<object>;
            if (list != null)
            {
                if (list.Count == 0) { sb.Append("[]"); return; }
                sb.Append("[\n");
                for (int k = 0; k < list.Count; k++)
                {
                    sb.Append(' ', indent + 2);
                    Write(sb, list[k], indent + 2);
                    sb.Append(k + 1 < list.Count ? ",\n" : "\n");
                }
                sb.Append(' ', indent).Append(']');
                return;
            }
            throw new ArgumentException("JSON_UNSUPPORTED_VALUE");
        }

        private static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        // Order-insensitive for object keys, exact for values and types.
        public static bool DeepEquals(object a, object b)
        {
            if (a is JsonNull || b is JsonNull) return a is JsonNull && b is JsonNull;
            if (a is bool && b is bool) return (bool)a == (bool)b;
            if (a is long && b is long) return (long)a == (long)b;
            if (a is double && b is double) return (double)a == (double)b;
            if (a is string && b is string) return string.Equals((string)a, (string)b, StringComparison.Ordinal);
            var oa = a as JsonObject;
            var ob = b as JsonObject;
            if (oa != null && ob != null)
            {
                if (oa.Count != ob.Count) return false;
                foreach (string key in oa.Keys)
                {
                    if (!ob.Has(key) || !DeepEquals(oa.Get(key), ob.Get(key))) return false;
                }
                return true;
            }
            var la = a as List<object>;
            var lb = b as List<object>;
            if (la != null && lb != null)
            {
                if (la.Count != lb.Count) return false;
                for (int k = 0; k < la.Count; k++)
                {
                    if (!DeepEquals(la[k], lb[k])) return false;
                }
                return true;
            }
            return false;
        }
    }
}
