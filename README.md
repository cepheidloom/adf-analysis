Login into azure cli using `az login` and then run the following command to fetch ADF details.
Azure cli command to get factory details.

```
az graph query -q "Resources | where type == 'microsoft.datafactory/factories' | join kind=leftouter (ResourceContainers | where type == 'microsoft.resources/subscriptions' | project subscriptionId, SubscriptionName=name) on subscriptionId | project FactoryName=name, ResourceGroup=resourceGroup, SubscriptionName, SubscriptionId=subscriptionId, Location=location" --query "data" --output table
```