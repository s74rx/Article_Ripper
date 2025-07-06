let capturedRequests = [];

chrome.webRequest.onBeforeRequest.addListener(
  function(details) {
    if (details.url.includes('cse') || 
        details.url.includes('search') || 
        details.url.includes('element') ||
        details.url.includes('googleapis')) {
      
      capturedRequests.push({
        url: details.url,
        method: details.method,
        timestamp: new Date().toISOString(),
        tabId: details.tabId
      });
      
      console.log('Captured API call:', details.url);
    }
  },
  {urls: ["<all_urls>"]},
  ["requestBody"]
);

chrome.storage.local.set({capturedRequests: capturedRequests});

