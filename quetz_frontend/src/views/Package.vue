<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
        <h2>Package: {{ name }}</h2>
        <p>
          {{ description }}
        </p>
          <!-- @search="onFilter" searchLabel="Filter" searchPlaceholder="Filter" searchClearLabel="Clear filter" -->
<!--           :pagination="pagination"
          @pagination="loadPagination"
 -->
        <h3>Available Versions</h3>
        <cv-data-table
          :columns="columns"
          :data="versionData"
          ref="table">
        </cv-data-table>
    </div>
  </div>
</div>
</template>

<script>
  export default {
    data() {
      return {
        name: "",
        description: "",
        versionData: [],
        columns: []
      };
    },
    methods: {
      fetchData() {
        let channel_id = this.$route.params.channel_id;
        let package_name = this.$route.params.package;

        fetch("/api/channels/" + channel_id + "/packages/" + package_name)
          .then(response => response.json())
          .then(data => {
            console.log(data);
            this.name = data.name;
            this.description = data.description;
          });

        fetch("/api/channels/" + channel_id + "/packages/" + package_name + "/versions")
          .then(response => response.json())
          .then(data => {
            this.columns = ["Version", "Platform", "Build String"]
            this.versionData = data.map((el) => {
              return [el.version, el.platform, el.build_string]
            })
          });
      },
    },
    created: function() {
      this.fetchData();
    },
  }
</script>

<style>
.white-svg {
  fill: white;
}

</style>

<style scoped>
h3 {
  margin: 2rem 0 1rem;
}
p {
  margin-top: 1.5rem 0 1.5rem;
}
tbody tr {
  cursor: pointer;
}
</style>