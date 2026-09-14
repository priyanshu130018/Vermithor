local pcall_str, str = pcall(require, "resty.string")
local pcall_hmac, hmac = pcall(require, "resty.hmac")
local cjson = require "cjson.safe"

local CLOCK_SKEW_TOLERANCE_SECONDS = 30

local function base64url_decode(input)
    local remainder = #input % 4
    if remainder > 0 then
        input = input .. string.rep("=", 4 - remainder)
    end
    input = input:gsub("-", "+"):gsub("_", "/")
    return ngx.decode_base64(input)
end

local function base64url_encode(input)
    local encoded = ngx.encode_base64(input)
    return encoded:gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end

local function return_unauthorized(internal_log_reason)
    local req_id = ngx.var.request_id or "unknown"
    if internal_log_reason then
        ngx.log(ngx.WARN, "[AUTH_FAILURE] req_id=", req_id, " reason=", internal_log_reason)
    end
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "application/json"
    ngx.header["X-Request-ID"] = req_id
    ngx.say(cjson.encode({
        error = "unauthorized",
        message = "Invalid authentication token",
        request_id = req_id
    }))
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

-- 1. Extract Authorization header
local auth_header = ngx.var.http_authorization
if not auth_header or not auth_header:match("^Bearer%s+(.+)$") then
    return_unauthorized("Missing or malformed Authorization header")
end

local token = auth_header:match("^Bearer%s+(.+)$")

-- 2. Split JWT into header, payload, signature
local parts = {}
for part in token:gmatch("[^%.]+") do
    table.insert(parts, part)
end

if #parts ~= 3 then
    return_unauthorized("Malformed JWT: invalid segment count")
end

local header_b64, payload_b64, signature_b64 = parts[1], parts[2], parts[3]

-- 3. Verify Header and Algorithm (Strict HS256 Only)
local header_json = base64url_decode(header_b64)
if not header_json then
    return_unauthorized("Invalid header base64url encoding")
end

local header = cjson.decode(header_json)
if not header or type(header) ~= "table" then
    return_unauthorized("Invalid header JSON structure")
end

if header.alg ~= "HS256" then
    return_unauthorized("Disallowed JWT algorithm: " .. tostring(header.alg))
end

-- 4. Verify Cryptographic Signature
local secret = os.getenv("JWT_SECRET") or "vermithor-dev-secret-key-32-chars-min"
local expected_sig = base64url_encode(ngx.hmac_sha256(secret, header_b64 .. "." .. payload_b64))

if expected_sig ~= signature_b64 then
    return_unauthorized("Signature mismatch")
end

-- 5. Parse Payload
local payload_json = base64url_decode(payload_b64)
if not payload_json then
    return_unauthorized("Invalid payload base64url encoding")
end

local payload = cjson.decode(payload_json)
if not payload or type(payload) ~= "table" then
    return_unauthorized("Invalid payload JSON structure")
end

-- 6. Verify Claims (Issuer, Audience, Timestamps with Clock Skew Tolerance)
local expected_issuer = os.getenv("JWT_ISSUER") or "vermithor"
local expected_audience = os.getenv("JWT_AUDIENCE") or "vermithor-api"

if payload.iss ~= expected_issuer then
    return_unauthorized("Invalid token issuer claim")
end

if payload.aud ~= expected_audience then
    return_unauthorized("Invalid token audience claim")
end

local current_time = ngx.time()

if payload.exp and (payload.exp + CLOCK_SKEW_TOLERANCE_SECONDS) < current_time then
    return_unauthorized("Token expired")
end

if payload.nbf and (payload.nbf - CLOCK_SKEW_TOLERANCE_SECONDS) > current_time then
    return_unauthorized("Token not yet valid (nbf)")
end

if payload.iat and (payload.iat - CLOCK_SKEW_TOLERANCE_SECONDS) > current_time then
    return_unauthorized("Token issued in future (iat)")
end

-- Success: propagate authenticated identity to upstream microservices
if payload.sub then
    ngx.req.set_header("X-User-ID", tostring(payload.sub))
end
ngx.req.set_header("X-Authenticated", "true")
