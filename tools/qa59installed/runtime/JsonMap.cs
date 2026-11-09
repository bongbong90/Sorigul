using System;
using System.Collections.Generic;

namespace Qa59Installed.Runtime
{
    // Construction adapter only; the contract's parsed JsonObject remains
    // read-only to separate assemblies. Serialize primitives with its encoder.
    internal sealed class JsonMap : Dictionary<string, object>
    {
        internal void TryAdd(string key, object value) { Add(key, value); }
        internal string Text() { return Encode(this); }
        internal JsonObject Parsed() { return (JsonObject)StrictJson.Parse(Text()); }
        private static string Encode(object value)
        {
            var map = value as JsonMap;
            if (map != null)
            {
                var parts = new List<string>();
                foreach (var pair in map) parts.Add(JsonText.Write(pair.Key) + ":" + Encode(pair.Value));
                return "{" + string.Join(",", parts.ToArray()) + "}";
            }
            var list = value as List<object>;
            if (list != null)
            {
                var parts = new List<string>();
                foreach (object item in list) parts.Add(Encode(item));
                return "[" + string.Join(",", parts.ToArray()) + "]";
            }
            if (value is string || value is bool || value is long || value is JsonNull) return JsonText.Write(value);
            throw new BoundaryException();
        }
    }
}
