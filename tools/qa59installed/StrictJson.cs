// Strict, bounded RFC 8259 reader for QA contract inputs. Pure: no I/O.
// Rejects duplicate keys, BOM, comments, trailing commas, NaN/Infinity,
// unpaired surrogates and oversize/overdeep input. Errors carry fixed codes
// only, never input text, so a rejection can be logged without leaking data.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Qa59Installed
{
    public sealed class JsonNull
    {
        public static readonly JsonNull Value = new JsonNull();
        private JsonNull() { }
    }

    public sealed class JsonObject
    {
        private readonly Dictionary<string, object> values = new Dictionary<string, object>(StringComparer.Ordinal);
        private readonly List<string> order = new List<string>();

        public IList<string> Keys { get { return order.AsReadOnly(); } }
        public int Count { get { return order.Count; } }
        public bool Has(string key) { return values.ContainsKey(key); }

        // C# null means the key is absent; JSON null is JsonNull.Value.
        public object Get(string key)
        {
            object value;
            return values.TryGetValue(key, out value) ? value : null;
        }

        internal bool TryAdd(string key, object value)
        {
            if (values.ContainsKey(key)) return false;
            values.Add(key, value);
            order.Add(key);
            return true;
        }

        internal void Replace(string key, object value)
        {
            if (!values.ContainsKey(key)) throw new KeyNotFoundException("JSON_KEY_NOT_FOUND");
            values[key] = value;
        }

        internal void Remove(string key)
        {
            if (values.Remove(key)) order.Remove(key);
        }
    }

    public sealed class JsonFormatException : Exception
    {
        public readonly string Code;
        public JsonFormatException(string code) : base(code) { Code = code; }
    }

    public static class StrictJson
    {
        public const int MaxLength = 1 << 20;
        public const int MaxDepth = 32;

        public static object Parse(string text)
        {
            if (text == null) throw new JsonFormatException("JSON_MISSING");
            if (text.Length > MaxLength) throw new JsonFormatException("JSON_TOO_LARGE");
            var reader = new Reader(text);
            reader.SkipWhitespace();
            object value = reader.ReadValue(0);
            reader.SkipWhitespace();
            if (!reader.AtEnd) throw new JsonFormatException("JSON_TRAILING_DATA");
            return value;
        }

        private sealed class Reader
        {
            private readonly string s;
            private int i;

            public Reader(string text) { s = text; }
            public bool AtEnd { get { return i >= s.Length; } }

            public void SkipWhitespace()
            {
                while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++;
            }

            private char Peek()
            {
                if (i >= s.Length) throw new JsonFormatException("JSON_UNEXPECTED_END");
                return s[i];
            }

            private void Expect(string literal)
            {
                if (i + literal.Length > s.Length || string.CompareOrdinal(s, i, literal, 0, literal.Length) != 0)
                    throw new JsonFormatException("JSON_INVALID_LITERAL");
                i += literal.Length;
            }

            public object ReadValue(int depth)
            {
                if (depth > MaxDepth) throw new JsonFormatException("JSON_TOO_DEEP");
                char c = Peek();
                switch (c)
                {
                    case '{': return ReadObject(depth);
                    case '[': return ReadArray(depth);
                    case '"': return ReadString();
                    case 't': Expect("true"); return true;
                    case 'f': Expect("false"); return false;
                    case 'n': Expect("null"); return JsonNull.Value;
                    default:
                        if (c == '-' || (c >= '0' && c <= '9')) return ReadNumber();
                        throw new JsonFormatException("JSON_UNEXPECTED_CHARACTER");
                }
            }

            private JsonObject ReadObject(int depth)
            {
                var result = new JsonObject();
                i++;
                SkipWhitespace();
                if (Peek() == '}') { i++; return result; }
                while (true)
                {
                    SkipWhitespace();
                    if (Peek() != '"') throw new JsonFormatException("JSON_EXPECTED_KEY");
                    string key = ReadString();
                    SkipWhitespace();
                    if (Peek() != ':') throw new JsonFormatException("JSON_EXPECTED_COLON");
                    i++;
                    SkipWhitespace();
                    object value = ReadValue(depth + 1);
                    if (!result.TryAdd(key, value)) throw new JsonFormatException("JSON_DUPLICATE_KEY");
                    SkipWhitespace();
                    char c = Peek();
                    i++;
                    if (c == '}') return result;
                    if (c != ',') throw new JsonFormatException("JSON_EXPECTED_COMMA");
                }
            }

            private List<object> ReadArray(int depth)
            {
                var result = new List<object>();
                i++;
                SkipWhitespace();
                if (Peek() == ']') { i++; return result; }
                while (true)
                {
                    SkipWhitespace();
                    result.Add(ReadValue(depth + 1));
                    SkipWhitespace();
                    char c = Peek();
                    i++;
                    if (c == ']') return result;
                    if (c != ',') throw new JsonFormatException("JSON_EXPECTED_COMMA");
                }
            }

            private string ReadString()
            {
                i++;
                var sb = new StringBuilder();
                while (true)
                {
                    char c = Peek();
                    i++;
                    if (c == '"') break;
                    if (c < 0x20) throw new JsonFormatException("JSON_CONTROL_CHARACTER");
                    if (c != '\\') { sb.Append(c); continue; }
                    char e = Peek();
                    i++;
                    switch (e)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u': sb.Append(ReadHex4()); break;
                        default: throw new JsonFormatException("JSON_INVALID_ESCAPE");
                    }
                }
                string value = sb.ToString();
                for (int k = 0; k < value.Length; k++)
                {
                    if (char.IsHighSurrogate(value[k]))
                    {
                        if (k + 1 >= value.Length || !char.IsLowSurrogate(value[k + 1]))
                            throw new JsonFormatException("JSON_UNPAIRED_SURROGATE");
                        k++;
                    }
                    else if (char.IsLowSurrogate(value[k]))
                    {
                        throw new JsonFormatException("JSON_UNPAIRED_SURROGATE");
                    }
                }
                return value;
            }

            private char ReadHex4()
            {
                if (i + 4 > s.Length) throw new JsonFormatException("JSON_INVALID_ESCAPE");
                int code = 0;
                for (int k = 0; k < 4; k++)
                {
                    char h = s[i + k];
                    int d = h >= '0' && h <= '9' ? h - '0'
                        : h >= 'a' && h <= 'f' ? h - 'a' + 10
                        : h >= 'A' && h <= 'F' ? h - 'A' + 10 : -1;
                    if (d < 0) throw new JsonFormatException("JSON_INVALID_ESCAPE");
                    code = code * 16 + d;
                }
                i += 4;
                return (char)code;
            }

            private object ReadNumber()
            {
                int start = i;
                bool isInteger = true;
                if (s[i] == '-') i++;
                if (Peek() == '0')
                {
                    i++;
                }
                else if (Peek() >= '1' && Peek() <= '9')
                {
                    while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++;
                }
                else
                {
                    throw new JsonFormatException("JSON_INVALID_NUMBER");
                }
                if (i < s.Length && s[i] == '.')
                {
                    isInteger = false;
                    i++;
                    if (i >= s.Length || s[i] < '0' || s[i] > '9') throw new JsonFormatException("JSON_INVALID_NUMBER");
                    while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++;
                }
                if (i < s.Length && (s[i] == 'e' || s[i] == 'E'))
                {
                    isInteger = false;
                    i++;
                    if (i < s.Length && (s[i] == '+' || s[i] == '-')) i++;
                    if (i >= s.Length || s[i] < '0' || s[i] > '9') throw new JsonFormatException("JSON_INVALID_NUMBER");
                    while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++;
                }
                string token = s.Substring(start, i - start);
                if (isInteger)
                {
                    long whole;
                    if (!long.TryParse(token, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out whole))
                        throw new JsonFormatException("JSON_INTEGER_OUT_OF_RANGE");
                    return whole;
                }
                double real;
                if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out real)
                    || double.IsInfinity(real) || double.IsNaN(real))
                    throw new JsonFormatException("JSON_INVALID_NUMBER");
                return real;
            }
        }
    }
}
