#include "ClosedLoopIdsClient.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <netdb.h>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <utility>

namespace {

std::string jsonEscape(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch; break;
        }
    }
    return out.str();
}

bool regexString(const std::string& json, const std::string& key, std::string& value) {
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (!std::regex_search(json, match, pattern)) return false;
    value = match[1].str();
    return true;
}

bool regexInt(const std::string& json, const std::string& key, int& value) {
    std::regex pattern("\"" + key + "\"\\s*:\\s*(-?\\d+)");
    std::smatch match;
    if (!std::regex_search(json, match, pattern)) return false;
    value = std::stoi(match[1].str());
    return true;
}

bool regexDouble(const std::string& json, const std::string& key, double& value) {
    std::regex pattern("\"" + key + "\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)");
    std::smatch match;
    if (!std::regex_search(json, match, pattern)) return false;
    value = std::stod(match[1].str());
    return true;
}

int connectSocket(const std::string& host, int port, int timeoutSeconds) {
    addrinfo hints {};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* result = nullptr;
    const std::string portText = std::to_string(port);
    int rc = getaddrinfo(host.c_str(), portText.c_str(), &hints, &result);
    if (rc != 0) {
        throw std::runtime_error(std::string("getaddrinfo failed: ") + gai_strerror(rc));
    }

    int sock = -1;
    for (addrinfo* rp = result; rp != nullptr; rp = rp->ai_next) {
        sock = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (sock == -1) continue;

        timeval timeout {};
        timeout.tv_sec = timeoutSeconds;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

        if (connect(sock, rp->ai_addr, rp->ai_addrlen) == 0) break;
        close(sock);
        sock = -1;
    }

    freeaddrinfo(result);
    if (sock == -1) {
        throw std::runtime_error("could not connect to IDS inference server");
    }
    return sock;
}

}  // namespace

ClosedLoopIdsClient::ClosedLoopIdsClient(std::string host, int port, int timeoutSeconds)
    : host_(std::move(host)), port_(port), timeoutSeconds_(timeoutSeconds) {}

IdsDecision ClosedLoopIdsClient::predictText(
    const std::string& vehicleId,
    double simTime,
    const std::string& textInput
) const {
    std::ostringstream body;
    body << "{"
         << "\"vehicle_id\":\"" << jsonEscape(vehicleId) << "\","
         << "\"sim_time\":" << simTime << ","
         << "\"text_input\":\"" << jsonEscape(textInput) << "\""
         << "}";
    return postPredict(body.str());
}

IdsDecision ClosedLoopIdsClient::predictFeatures(
    const std::string& vehicleId,
    double simTime,
    const std::map<std::string, std::string>& features
) const {
    std::ostringstream body;
    body << "{"
         << "\"vehicle_id\":\"" << jsonEscape(vehicleId) << "\","
         << "\"sim_time\":" << simTime << ","
         << "\"features\":{";
    bool first = true;
    for (const auto& item : features) {
        if (!first) body << ",";
        first = false;
        body << "\"" << jsonEscape(item.first) << "\":\"" << jsonEscape(item.second) << "\"";
    }
    body << "}}";
    return postPredict(body.str());
}

IdsDecision ClosedLoopIdsClient::postPredict(const std::string& body) const {
    IdsDecision decision;
    try {
        int sock = connectSocket(host_, port_, timeoutSeconds_);
        std::ostringstream request;
        request << "POST /predict HTTP/1.1\r\n"
                << "Host: " << host_ << ":" << port_ << "\r\n"
                << "Content-Type: application/json\r\n"
                << "Content-Length: " << body.size() << "\r\n"
                << "Connection: close\r\n\r\n"
                << body;

        const std::string requestText = request.str();
        ssize_t sent = send(sock, requestText.data(), requestText.size(), 0);
        if (sent < 0) {
            close(sock);
            throw std::runtime_error(std::string("send failed: ") + std::strerror(errno));
        }

        std::string response;
        char buffer[4096];
        while (true) {
            ssize_t n = recv(sock, buffer, sizeof(buffer), 0);
            if (n <= 0) break;
            response.append(buffer, buffer + n);
        }
        close(sock);

        const std::string marker = "\r\n\r\n";
        const std::size_t bodyStart = response.find(marker);
        decision.rawJson = bodyStart == std::string::npos ? response : response.substr(bodyStart + marker.size());
        decision.ok = regexInt(decision.rawJson, "predicted_label", decision.predictedLabel)
            && regexDouble(decision.rawJson, "confidence", decision.confidence)
            && regexString(decision.rawJson, "attack_name", decision.attackName)
            && regexString(decision.rawJson, "action", decision.action);
    } catch (const std::exception& exc) {
        decision.ok = false;
        decision.error = exc.what();
    }
    return decision;
}
