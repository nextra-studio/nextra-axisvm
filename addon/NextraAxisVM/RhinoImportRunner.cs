using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using AxisVM;
using AxisVM_plugin.Core;

namespace NextraAxisVM
{
    /// <summary>
    /// Headless Rhino import: the same AxisModelBuilder as the "N. Rhino Import" add-on (vendored in RhinoImport/),
    /// driven by options instead of a dialog, reporting as JSON instead of a report window.
    /// One SaveUndo + BeginUpdate/EndUpdate pair wraps the build, so one AxisVM undo step reverts the whole import.
    /// </summary>
    internal static class RhinoImportRunner
    {
        internal static string Run(object appObj, string jsonPath, string optionsJson)
        {
            var app = (IAxisVMApplication)appObj;
            IAxisVMModel model = app.Models.Item[1];
            if (model == null) return "{\"ok\": false, \"error\": \"no AxisVM model is open\"}";
            if (!File.Exists(jsonPath)) return "{\"ok\": false, \"error\": " + Json.Str("file not found: " + jsonPath) + "}";

            JsonValue opt = string.IsNullOrWhiteSpace(optionsJson) ? null : JsonValue.Parse(optionsJson);
            var notes = new List<string>();
            JsonValue root = JsonValue.Parse(File.ReadAllText(jsonPath));
            RhinoModel rhino = RhinoModel.FromJson(root, notes);
            foreach (string w in rhino.ExportWarnings) notes.Add("Rhino export warning: " + w);

            // Units: explicit option, else the Rhino document unit system written by the exporter (mm or m).
            JsonValue source = root["source"];
            string unitSystem = source != null ? source["unitSystem"].AsStringSafe("") : "";
            string length = Opt(opt, "length", "");
            int li = length == "m" ? 1 : length == "mm" ? 0 : AxUnits.LengthIndexFromRhinoName(unitSystem);
            if (!AxUnits.IsSupportedRhinoUnit(unitSystem) && length == "")
                notes.Add("Rhino unit system '" + unitSystem + "' is not mm or m; read as mm. Pass length:'m' or 'mm' to override.");
            string force = Opt(opt, "force", "kN");
            var units = new AxUnits
            {
                LengthToM = AxUnits.LengthUnitFactors[li],
                LengthName = AxUnits.LengthUnitNames[li],
                ForceSystem = force.StartsWith("N", StringComparison.OrdinalIgnoreCase) && !force.StartsWith("kN", StringComparison.OrdinalIgnoreCase) ? 1 : 0,
            };
            units.ForceName = units.ForceSystem == 1 ? "N, mm" : "kN, m";

            double tolMm = OptD(opt, "tol_mm", 1.0);
            var options = new ImportOptions
            {
                Units = units,
                MergeToleranceM = tolMm / 1000.0,
                DryRun = OptB(opt, "dry_run", false),
                AutoIntersect = OptB(opt, "auto_intersect", true),
                SourcePath = jsonPath,
            };

            var builder = new AxisModelBuilder(app, model, rhino, options, notes);
            if (options.DryRun) builder.Run();
            else
            {
                try { model.SaveUndo("Nextra Rhino import"); } catch { notes.Add("no undo step could be recorded"); }
                model.BeginUpdate();
                try { builder.Run(); }
                finally { model.EndUpdate(); try { model.Refresh(); } catch { } }
            }

            ImportStats s = builder.Stats;
            var sb = new StringBuilder("{\"ok\": true");
            sb.Append(", \"dry_run\": ").Append(options.DryRun ? "true" : "false");
            sb.Append(", \"units\": ").Append(Json.Str(units.LengthName + " lengths, " + units.ForceName + " loads"));
            sb.Append(", \"read\": {\"points\": ").Append(rhino.Points.Count).Append(", \"lines\": ").Append(rhino.Lines.Count)
              .Append(", \"surfaces\": ").Append(rhino.Domains.Count).Append("}");
            sb.Append(", \"created\": {");
            sb.Append("\"nodes\": ").Append(s.NodesCreated).Append(", \"nodes_shared\": ").Append(s.NodesShared);
            sb.Append(", \"lines\": ").Append(s.LinesCreated).Append(", \"lines_merged\": ").Append(s.LinesMerged).Append(", \"lines_split\": ").Append(s.LinesSplit);
            sb.Append(", \"domains\": ").Append(s.DomainsCreated).Append(", \"holes\": ").Append(s.HolesCreated);
            sb.Append(", \"load_panels\": ").Append(s.PanelsCreated);
            sb.Append(", \"nodal_supports\": ").Append(s.SupportsCreated).Append(", \"line_supports\": ").Append(s.LineSupportsCreated);
            sb.Append(", \"springs\": ").Append(s.SpringsCreated).Append(", \"links\": ").Append(s.LinksCreated).Append(", \"rigid_bodies\": ").Append(s.RigidBodiesCreated);
            sb.Append(", \"edge_hinges\": ").Append(s.HingesCreated).Append(", \"loads\": ").Append(s.LoadsCreated).Append(", \"parts\": ").Append(s.PartsCreated);
            sb.Append(", \"members_assembled\": ").Append(s.MembersAssembled).Append("}");
            sb.Append(", \"attribute_errors\": ").Append(s.AttributeErrors);
            sb.Append(", \"notes\": [");
            for (int i = 0; i < notes.Count; i++) { if (i > 0) sb.Append(", "); sb.Append(Json.Str(notes[i])); }
            sb.Append("]}");
            return sb.ToString();
        }

        static string Opt(JsonValue o, string key, string def)
        {
            if (o == null || o[key] == null) return def;
            var v = o[key];
            return v.Type == JsonValue.JsonType.String ? v.StringValue : def;
        }

        static double OptD(JsonValue o, string key, double def) { return o == null || o[key] == null ? def : o[key].AsDouble(def); }

        static bool OptB(JsonValue o, string key, bool def)
        {
            if (o == null || o[key] == null) return def;
            var v = o[key];
            return v.Type == JsonValue.JsonType.Bool ? v.BoolValue : def;
        }

        static string AsStringSafe(this JsonValue v, string def) { return v == null ? def : v.AsString(def); }
    }
}
