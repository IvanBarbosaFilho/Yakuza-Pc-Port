// Yakuza (SLUS_213.48): optional over-the-shoulder camera, after Rule of Rose's (~/PS2/ror/mods). It only moves the
// camera the street is drawn with: controls, game logic and every other camera (talks, events, fights' own
// cameras) are untouched.
//
// Camera pipeline (reverse engineered 2026-11-15, see HANDOFF "shoulder camera"):
// - The game camera is entity 919 (*(0x1572a0) + 0x2e8 + 4 * 919, gamecamera.cpp). Its update FUN_002e0e80 (ovl_main,
//   called through the entity's vtable) picks the eye 0x622340 and the target 0x622350 for its mode (byte
//   +0x1eb0), sets the control heading 0x1572c8 = atan2(target - eye) (0x10000 per turn) and at its end
//   (0x2e1ce8) builds the view with FUN_00188c20(eye, target, roll 0x1572d8), stored at 0x622360 / 0x6223a0.
// - The player is entity 8; its vtable (+0x70) getters, in the ogre4 overlay of the area: +0x128 returns the
//   position (addiu v0, a0, 0x550), +0x138 the facing angle (lw v0, 0x1548(a0)). The offsets are read from
//   those instructions, so another overlay with other offsets still works (or the camera stays off).
// The wrapper on FUN_00188c20 swaps eye and target only for its two calls at the end of FUN_002e0e80 (return
// addresses 0x2e1d0c / 0x2e1d54, $s1 = the camera entity; a flag set by a wrapper on FUN_002e0e80 was lost when
// the scheduler unwound and resumed the function midway), then puts the game's back:
// the follow camera keeps its own state.
// Heading: ours. The right stick turns it; with the right stick idle it eases behind Kiryu's direction of motion.
// The left stick is rotated by (our control heading - the game camera's heading) in the pad layer, so the game's
// camera-relative movement follows our camera; it is latched while the stick is held in one direction.
// Camera modes (byte +0x1eb0, play log 2026-11-15): 14 walking the streets, 4 the corner / crossing cameras,
// 3 fights, 2 the encounter intro, 7 talks.
//
// Switch "shoulder": PS2X_SHOULDER=1 starts it on; the options menu (F2 / L3) toggles it.
// Tuning (game units, ~10 cm): PS2X_SHOULDER_BACK (22), _SIDE (5), _HEIGHT (18), _AHEAD (30), _AIM_HEIGHT (15),
// _BLEND_FRAMES (20), _TURN (0.05 rad/frame), _RECENTER (0.035), _RECENTER_DELAY (40 frames), _INVERT (0);
// PS2X_SHOULDER_MODES=<list> the camera modes it applies in (default 3,4,8,9,13,14,17).
#include "game_overrides.h"
#include "ps2_runtime.h"
#include "ps2_mod_menu.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

std::atomic<bool> &ps2xSwitchFlag(const char *name); // ps2_runtime.cpp
// Pad hooks (ps2_pad.cpp): the raw sticks, the right stick taken from the game, the left stick's rotation.
extern std::atomic<float> g_ps2xLeftStickRotation;
extern std::atomic<bool> g_ps2xRightStickTaken;
extern std::atomic<float> g_ps2xRightStickX;
extern std::atomic<float> g_ps2xLeftStickX;
extern std::atomic<float> g_ps2xLeftStickY;
extern std::atomic<bool> g_ps2xMouseMotionWanted; // ps2_pad.cpp: capture the mouse for us
extern std::atomic<float> g_ps2xMouseDeltaX, g_ps2xMouseDeltaY;

namespace
{
    constexpr uint32_t kViewCallReturnA = 0x002e1d0cu; // FUN_002e0e80's lookAt calls (the street camera's view)
    constexpr uint32_t kViewCallReturnB = 0x002e1d54u;
    constexpr uint32_t kLookAtFn = 0x00188c20u;       // FUN_00188c20(eye, target, roll)
    constexpr uint32_t kEntityRoot = 0x001572a0u;
    constexpr uint32_t kCameraEntity = 919u;
    constexpr uint32_t kPlayerEntity = 8u;
    constexpr uint32_t kModeField = 0x1eb0u;


    struct Vec3
    {
        float x, y, z;
    };
    Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
    Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
    Vec3 operator*(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
    float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
    bool finite(Vec3 v) { return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z); }

    float envFloat(const char *name, float fallback)
    {
        const char *value = std::getenv(name);
        return value ? std::strtof(value, nullptr) : fallback;
    }

    uint32_t readWord(const uint8_t *rdram, uint32_t address)
    {
        uint32_t value = 0u;
        std::memcpy(&value, rdram + (address & 0x1FFFFFCu), sizeof(value));
        return value;
    }

    Vec3 readVec(const uint8_t *rdram, uint32_t address)
    {
        Vec3 v;
        std::memcpy(&v, rdram + (address & 0x1FFFFF0u), sizeof(v));
        return v;
    }

    void writeVec(uint8_t *rdram, uint32_t address, Vec3 v)
    {
        std::memcpy(rdram + (address & 0x1FFFFF0u), &v, sizeof(v));
    }

    bool inRam(uint32_t address) { return (address & 0x1FFFFFFu) >= 0x100000u && (address & 0x1FFFFFFu) < 0x1FF0000u; }

    uint32_t entity(const uint8_t *rdram, uint32_t index)
    {
        const uint32_t root = readWord(rdram, kEntityRoot);
        return inRam(root) ? readWord(rdram, root + 0x2e8u + 4u * index) : 0u;
    }

    // Field offset a one-instruction getter reads: "jr ra" + delay slot "addiu v0, a0, imm" (wantLoad false) or
    // "lw v0, imm(a0)" (true). 0 when the getter is something else.
    uint32_t getterOffset(const uint8_t *rdram, uint32_t function, bool wantLoad)
    {
        if (!inRam(function))
            return 0u;
        const uint32_t first = readWord(rdram, function), second = readWord(rdram, function + 4u);
        const uint32_t expected = wantLoad ? 0x8c820000u : 0x24820000u;
        if (first != 0x03e00008u || (second & 0xffff0000u) != expected)
            return 0u;
        return second & 0xffffu;
    }

    float angleDelta(float from, float to) { return std::remainder(to - from, 6.2831853f); }

    struct State
    {
        bool active = false; // applied last frame
        float blend = 1.0f;  // 0 -> 1: from the game's camera to ours
        float outBlend = 1.0f;
        Vec3 lastEye{}, lastTarget{};
        bool hasLast = false;
        uint32_t lastMode = 0xffffffffu;
        float camYaw = 0.0f;     // our heading (radians, atan2(x, z) like the game's 0x1572c8)
        float controlYaw = 0.0f; // heading the left stick is relative to (latched while the stick is held)
        float latchedStick = 0.0f;
        bool latched = false;
        Vec3 lastFeet{};
        uint32_t idleStickFrames = 0u;
        float pitch = 0.0f; // mouse: look up (+) / down (-), radians
        uint32_t releasedFrames = 1000u; // frames since the last release (short mode blips keep the heading)
        bool keepHeading = false;        // released for a Heat Action: come back with the same heading
    } g_state;

    bool modeAllowed(uint32_t mode)
    {
        static const std::string modes = []()
        {
            const char *value = std::getenv("PS2X_SHOULDER_MODES");
            return std::string(",") + (value ? value : "3,4,8,9,13,14,17") + ",";
        }();
        return modes.find("," + std::to_string(mode) + ",") != std::string::npos;
    }

    float smooth(float t) { return t * t * (3.0f - 2.0f * t); }

    // Presented frames since our camera last ran: when the street camera stops being updated (cutscenes with
    // their own camera, loading), the frame hook hands the sticks back.
    std::atomic<uint32_t> g_framesSincePose{0u};
    std::atomic<bool> g_controlsTaken{false};

    // Mouse sensitivity choices (radians per pixel), option "Mouse sensitivity".
    constexpr float kMouseSens[] = {0.0012f, 0.0020f, 0.0030f, 0.0045f};
    std::atomic<int> g_mouseSens{1};

    void releaseControls()
    {
        g_ps2xMouseMotionWanted.store(false, std::memory_order_relaxed);
        g_controlsTaken.store(false, std::memory_order_relaxed);
        g_ps2xLeftStickRotation.store(0.0f, std::memory_order_relaxed);
        g_ps2xRightStickTaken.store(false, std::memory_order_relaxed);
    }

    // Our eye and target for this frame, or false (keep the game's).
    bool shoulderPose(uint8_t *rdram, uint32_t camera, Vec3 gameEye, Vec3 gameTarget, Vec3 &eye, Vec3 &target)
    {
        State &state = g_state;
        static std::atomic<bool> &enabled = ps2xSwitchFlag("shoulder");
        const uint32_t mode = rdram[(camera + kModeField) & 0x1FFFFFFu];
        if (mode != state.lastMode)
        {
            std::cerr << "[shoulder] camera mode " << mode << (modeAllowed(mode) ? " (shoulder)" : " (game camera)")
                      << std::endl;
            state.lastMode = mode;
        }
        // PS2X_SHOULDER_TRACE=1: logs the camera fields that change in fights (finding what marks a Heat Action).
        static const bool trace = envFloat("PS2X_SHOULDER_TRACE", 0.0f) != 0.0f;
        if (trace && enabled.load(std::memory_order_relaxed))
        {
            struct Field
            {
                const char *name;
                uint32_t address;
                bool global;
            };
            static const Field fields[] = {{"cam+0x7c", 0x7cu, false},    {"cam+0x210", 0x210u, false},
                                           {"cam+0x214", 0x214u, false},  {"cam+0x218", 0x218u, false},
                                           {"cam+0x21c", 0x21cu, false},  {"cam+0x22c", 0x22cu, false},
                                           {"cam+0x1b40", 0x1b40u, false}, {"cam+0x1eb0", 0x1eb0u, false},
                                           {"fov 0x1572d4", 0x1572d4u, true}, {"0x1571c8", 0x1571c8u, true},
                                           {"0x157428", 0x157428u, true}, {"0x157330", 0x157330u, true},
                                           {"0x1572e8", 0x1572e8u, true}, {"0x1572f4", 0x1572f4u, true}};
            static uint32_t last[sizeof(fields) / sizeof(fields[0])] = {};
            static uint64_t frame = 0u;
            ++frame;
            for (size_t n = 0; n < sizeof(fields) / sizeof(fields[0]); ++n)
            {
                const uint32_t value = readWord(rdram, fields[n].global ? fields[n].address : camera + fields[n].address);
                if (value != last[n])
                {
                    std::cerr << "[shoulder:trace] f" << frame << " mode " << mode << " " << fields[n].name << " 0x"
                              << std::hex << last[n] << " -> 0x" << value << std::dec << std::endl;
                    last[n] = value;
                }
            }
        }
        const uint32_t player = entity(rdram, kPlayerEntity);
        // cam+0x7c != 0: an external camera drives the view (FUN_002e0e80 skips its modes): Heat Actions, ~2 s
        // each (trace of 3 Heat Actions, Ivan 2026-11-15). Hand it the view and come back with our heading.
        const bool external = readWord(rdram, camera + 0x7cu) != 0u;
        if (external)
            state.keepHeading = true;
        bool apply = enabled.load(std::memory_order_relaxed) && modeAllowed(mode) && inRam(player) && !external;
        Vec3 feet{};
        if (apply)
        {
            const uint32_t vtable = readWord(rdram, player + 0x70u);
            const uint32_t positionOffset = inRam(vtable) ? getterOffset(rdram, readWord(rdram, vtable + 0x128u), false) : 0u;
            if (!positionOffset)
            {
                static bool reported = false;
                if (!reported)
                    std::cerr << "[shoulder] player position getter not recognised: game camera" << std::endl;
                reported = true;
                apply = false;
            }
            else
            {
                feet = readVec(rdram, player + positionOffset);
                apply = finite(feet);
            }
        }
        // The game camera's heading: the left stick is relative to it in the game.
        Vec3 gameHeading = gameTarget - gameEye;
        gameHeading.y = 0.0f;
        if (!(dot(gameHeading, gameHeading) > 1e-6f))
            apply = false;
        if (!apply)
        {
            if (state.active)
            {
                state.active = false;
                state.outBlend = 0.0f;
                state.releasedFrames = 0u;
                releaseControls();
                std::cerr << "[shoulder] released" << std::endl;
            }
            if (state.releasedFrames < 1000u)
                ++state.releasedFrames;
            // Glide back from the last shoulder pose to the game's camera.
            static const float frames = std::max(1.0f, envFloat("PS2X_SHOULDER_BLEND_FRAMES", 20.0f));
            if (state.outBlend < 1.0f && state.hasLast && enabled.load(std::memory_order_relaxed))
            {
                state.outBlend = std::min(1.0f, state.outBlend + 1.0f / frames);
                const float t = smooth(state.outBlend);
                eye = state.lastEye + (gameEye - state.lastEye) * t;
                target = state.lastTarget + (gameTarget - state.lastTarget) * t;
                return state.outBlend < 1.0f;
            }
            return false;
        }

        static const float back = envFloat("PS2X_SHOULDER_BACK", 22.0f);
        static const float side = envFloat("PS2X_SHOULDER_SIDE", 5.0f);
        static const float height = envFloat("PS2X_SHOULDER_HEIGHT", 18.0f);
        static const float ahead = envFloat("PS2X_SHOULDER_AHEAD", 30.0f);
        static const float aimHeight = envFloat("PS2X_SHOULDER_AIM_HEIGHT", 15.0f);
        static const float frames = std::max(1.0f, envFloat("PS2X_SHOULDER_BLEND_FRAMES", 20.0f));
        static const float turnSpeed = envFloat("PS2X_SHOULDER_TURN", 0.05f);    // rad per frame, full stick
        static const float recenter = envFloat("PS2X_SHOULDER_RECENTER", 0.035f); // share per frame
        static const uint32_t recenterDelay = static_cast<uint32_t>(envFloat("PS2X_SHOULDER_RECENTER_DELAY", 40.0f));
        static const float invert = envFloat("PS2X_SHOULDER_INVERT", 0.0f) != 0.0f ? -1.0f : 1.0f;

        const float gameYaw = std::atan2(gameHeading.x, gameHeading.z);
        if (!state.active)
        {
            state.active = true;
            state.blend = 0.0f;
            // A short blip (corner camera switch, a frame of another mode) keeps our heading; otherwise start
            // where the game's camera looks.
            if (state.releasedFrames > 30u && !state.keepHeading)
                state.camYaw = gameYaw;
            state.keepHeading = false;
            state.controlYaw = state.camYaw;
            state.latched = false;
            state.lastFeet = feet;
            state.idleStickFrames = 0u;
            state.pitch = 0.0f;
            g_ps2xMouseDeltaX.store(0.0f, std::memory_order_relaxed); // motion from before does not count
            g_ps2xMouseDeltaY.store(0.0f, std::memory_order_relaxed);
            std::cerr << "[shoulder] applied (camera mode " << mode << ")" << std::endl;
        }

        // Right stick turns the camera (taken from the game while applied).
        g_framesSincePose.store(0u, std::memory_order_relaxed);
        g_controlsTaken.store(true, std::memory_order_relaxed);
        g_ps2xRightStickTaken.store(true, std::memory_order_relaxed);
        const float rx = g_ps2xRightStickX.load(std::memory_order_relaxed);
        if (std::fabs(rx) > 0.15f)
        {
            state.camYaw += rx * turnSpeed * invert;
            state.idleStickFrames = 0u;
        }
        else
            ++state.idleStickFrames;
        // Mouse (switch "shouldernomouse" off = mouse camera on, the default): the motion turns the camera as an
        // angle (pixels x sensitivity), horizontally and a little vertically; it holds the heading like the stick.
        static std::atomic<bool> &noMouse = ps2xSwitchFlag("shouldernomouse");
        g_ps2xMouseMotionWanted.store(!noMouse.load(std::memory_order_relaxed), std::memory_order_relaxed);
        {
            static const float invertY = envFloat("PS2X_MOUSE_INVERT_Y", 0.0f) != 0.0f ? -1.0f : 1.0f;
            const float sens = kMouseSens[std::clamp(g_mouseSens.load(std::memory_order_relaxed), 0, 3)];
            const float dx = g_ps2xMouseDeltaX.exchange(0.0f, std::memory_order_relaxed);
            const float dy = g_ps2xMouseDeltaY.exchange(0.0f, std::memory_order_relaxed);
            if (dx != 0.0f || dy != 0.0f)
            {
                state.camYaw += dx * sens;
                state.pitch = std::clamp(state.pitch - dy * sens * invertY, -0.30f, 0.45f);
                state.idleStickFrames = 0u;
            }
        }

        // Ease behind Kiryu while he walks (his direction of motion), once the right stick has been left alone.
        // Only while the left stick is held (attacks, hits and animations move him too) and never in fights
        // (modes 3 and 8: every punch steps forward and turned the camera, Ivan 2026-11-15).
        const float lx = g_ps2xLeftStickX.load(std::memory_order_relaxed);
        const float ly = g_ps2xLeftStickY.load(std::memory_order_relaxed);
        const bool walking = lx * lx + ly * ly >= 0.09f;
        const bool fight = mode == 3u || mode == 8u;
        Vec3 moved = feet - state.lastFeet;
        moved.y = 0.0f;
        state.lastFeet = feet;
        const float speed2 = dot(moved, moved);
        if (speed2 > 400.0f) // a teleport (scene change): no recentering on it
            moved = Vec3{0.0f, 0.0f, 0.0f};
        else if (!fight && walking && state.idleStickFrames > recenterDelay && speed2 > 0.0025f)
        {
            const float motionYaw = std::atan2(moved.x, moved.z);
            const float delta = angleDelta(state.camYaw, motionYaw);
            // Slower when he comes toward the camera (a full turn around him would be abrupt).
            const float rate = std::fabs(delta) > 2.3f ? recenter * 0.35f : recenter;
            state.camYaw += delta * rate;
        }
        state.camYaw = std::remainder(state.camYaw, 6.2831853f);

        // Controls: the left stick is relative to controlYaw. It follows the camera while the stick is at rest
        // and stays latched while the stick is held in the same direction, so holding "right" walks a straight
        // line while the camera swings behind him (instead of circling with it).
        if (!walking)
        {
            state.latched = false;
            state.controlYaw = state.camYaw;
        }
        else
        {
            const float stick = std::atan2(lx, -ly);
            if (!state.latched || std::fabs(angleDelta(state.latchedStick, stick)) > 0.8f)
            {
                state.latched = true;
                state.latchedStick = stick;
                state.controlYaw = state.camYaw;
            }
        }
        // (x, up) rotated by a turns "up" toward the right for a > 0: the heading a radians to the right.
        g_ps2xLeftStickRotation.store(angleDelta(gameYaw, state.controlYaw), std::memory_order_relaxed);

        const Vec3 heading{std::sin(state.camYaw), 0.0f, std::cos(state.camYaw)};
        const Vec3 right{heading.z, 0.0f, -heading.x}; // Y up: right of the heading
        eye = feet + Vec3{0.0f, height, 0.0f} - heading * back + right * side;
        target = feet + Vec3{0.0f, aimHeight, 0.0f} + heading * ahead + right * side;
        // Mouse pitch: the target moves up or down by the angle, seen from the eye.
        if (state.pitch != 0.0f)
            target.y += std::tan(state.pitch) * (back + ahead);

        if (state.blend < 1.0f)
        {
            state.blend = std::min(1.0f, state.blend + 1.0f / frames);
            const float t = smooth(state.blend);
            eye = gameEye + (eye - gameEye) * t;
            target = gameTarget + (target - gameTarget) * t;
        }
        state.lastEye = eye;
        state.lastTarget = target;
        state.hasLast = true;
        state.outBlend = 1.0f;
        return true;
    }

    // ovl_main's own function (resident whenever these run: they are only reached through its code).
    void callOriginal(uint32_t address, uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (PS2Runtime::RecompiledFunction original = runtime->overlayOriginal(address))
            original(rdram, ctx, runtime);
        else
            std::cerr << "[shoulder] 0x" << std::hex << address << std::dec << " not resident" << std::endl;
    }

    void lookAt(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t ra = GPR_U32(ctx, 31);
        const uint32_t camera = GPR_U32(ctx, 17); // $s1 in FUN_002e0e80
        if ((ra != kViewCallReturnA && ra != kViewCallReturnB) || camera != entity(rdram, kCameraEntity))
        {
            callOriginal(kLookAtFn, rdram, ctx, runtime);
            return;
        }
        const uint32_t eyeAt = GPR_U32(ctx, 4), targetAt = GPR_U32(ctx, 5);
        const Vec3 gameEye = readVec(rdram, eyeAt), gameTarget = readVec(rdram, targetAt);
        Vec3 eye, target;
        if (!finite(gameEye) || !finite(gameTarget) || !shoulderPose(rdram, camera, gameEye, gameTarget, eye, target))
        {
            callOriginal(kLookAtFn, rdram, ctx, runtime);
            return;
        }
        writeVec(rdram, eyeAt, eye);
        writeVec(rdram, targetAt, target);
        callOriginal(kLookAtFn, rdram, ctx, runtime);
        // The game's camera state stays its own (the follow code and the control heading read these).
        writeVec(rdram, eyeAt, gameEye);
        writeVec(rdram, targetAt, gameTarget);
    }

    void apply(PS2Runtime &runtime)
    {
        // ovl_main is loaded from the disc later: the replacements are registered for its addresses now.
        if (!runtime.replaceFunction(kLookAtFn, &lookAt))
        {
            std::cerr << "[shoulder] camera functions not replaceable: not installed" << std::endl;
            return;
        }
        ps2x_menu::addSwitch("shoulder", "Over-the-shoulder camera", "shoulder", false,
                             "Camera behind Kiryu in the streets and fights. Right stick or mouse turns it.", 30);
        ps2x_menu::addSwitch("shouldermouse", "Mouse camera", "shouldernomouse", true,
                             "With the shoulder camera: the mouse turns it (the cursor is captured).", 31);
        {
            ps2x_menu::Option sens;
            sens.key = "mousesens";
            sens.label = "Mouse sensitivity";
            sens.help = "How far the shoulder camera turns per mouse movement.";
            sens.choices = {"Low", "Medium", "High", "Very high"};
            sens.get = []() { return g_mouseSens.load(); };
            sens.set = [](int index) { g_mouseSens.store(index); };
            sens.order = 32;
            ps2x_menu::addOption(std::move(sens));
        }
        ps2x_menu::addFrameHook([]()
        {
            if (g_controlsTaken.load(std::memory_order_relaxed) &&
                g_framesSincePose.fetch_add(1u, std::memory_order_relaxed) > 6u)
            {
                releaseControls();
                std::cerr << "[shoulder] street camera idle: sticks handed back" << std::endl;
            }
        });
        std::cerr << "[shoulder] over-the-shoulder camera available (options menu; PS2X_SHOULDER=1 starts on)"
                  << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("Yakuza shoulder camera", "SLUS_213.48", 0u, 0u, apply)
