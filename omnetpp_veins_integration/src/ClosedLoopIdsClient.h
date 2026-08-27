#pragma once

#include <map>
#include <string>

struct IdsDecision {
    bool ok = false;
    int predictedLabel = -1;
    double confidence = 0.0;
    std::string attackName;
    std::string action;
    std::string rawJson;
    std::string error;
};

class ClosedLoopIdsClient {
  public:
    ClosedLoopIdsClient(std::string host = "127.0.0.1", int port = 9090, int timeoutSeconds = 2);

    IdsDecision predictText(const std::string& vehicleId, double simTime, const std::string& textInput) const;
    IdsDecision predictFeatures(
        const std::string& vehicleId,
        double simTime,
        const std::map<std::string, std::string>& features
    ) const;

  private:
    std::string host_;
    int port_;
    int timeoutSeconds_;

    IdsDecision postPredict(const std::string& body) const;
};
