// Example hook for a Veins application module.
//
// Copy ClosedLoopIdsClient.h/.cc into your Veins project, add the .cc file to
// the build, then call the helper from your vehicle application or SDN
// controller when a BSM/CAM/event is processed.

#include "../src/ClosedLoopIdsClient.h"

#include <map>
#include <string>

void exampleClosedLoopCall() {
    ClosedLoopIdsClient ids("127.0.0.1", 9090, 2);

    std::map<std::string, std::string> features {
        {"run", "veins_closed_loop"},
        {"density", "1"},
        {"ratio", "0"},
        {"time_cs", "1200"},
        {"sender", "veh_00001"},
        {"seq", "42"},
        {"x_cm", "25000"},
        {"y_cm", "0"},
        {"speed_cms", "700"},
        {"accel_cms2", "20"},
        {"heading_cdeg", "9000"},
        {"lane", "0"},
        {"event", "0"},
    };

    IdsDecision decision = ids.predictFeatures("veh_00001", 12.0, features);
    if (!decision.ok) {
        // In a simulation module, use EV_WARN and keep the default behavior.
        return;
    }

    if (decision.action == "allow") {
        // Forward/process the message normally.
    } else if (decision.action == "monitor") {
        // Increase sender trust penalty but do not block yet.
    } else if (decision.action == "isolate_sender") {
        // Ask SDN controller/RSU logic to isolate this sender.
    } else {
        // Drop suspicious message or reroute according to your SDN policy.
    }
}
