<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
        <h3 class="bx--data-table-header">Jobs on the server</h3>
        <cv-data-table
          :columns="columns"
          :data="table_data"
          ref="table">
        </cv-data-table>
    </div>
  </div>
</div>
</template>

<script>

export default {
  data: function () {
    return {
      columns: [],
      table_data: [],
      loading: true
    }
  },
  methods: {
    // TODO double request currently, also save value of #packages to display in local storage?
    load: function() {
      let url = "/api/jobs"
      return fetch(url).then((msg) => {
        return msg.json().then((decoded) => {
            console.log(decoded);
            this.columns = ["Name", "Created", "Selector", "Status", "Creator"];
            this.raw_data = decoded
            this.table_data = decoded.map((el) => [el.manifest, el.created, el.items_spec, el.status, el.owner.username]);
        });
      });
    },
    attachEvents: function() {
      let router = this.$router;
      this.$el.querySelectorAll('tr').forEach((el) => {
        el.addEventListener('click', () => {
          router.push({
            path: '/jobs/' + this.raw_data[el.getAttribute('value')].id
          });
        });
      });
    },
  },
  created: function() {
    this.load()
  },
  updated() {
    this.attachEvents();
  }
}
</script>

<style>
html {
  height: 100%;
}
#app {
  min-height: 100%;
}
</style>
